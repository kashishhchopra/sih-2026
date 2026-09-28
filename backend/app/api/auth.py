import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.ratelimit import login_rate_limit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.core.time import utc_now
from app.db.session import get_db
from app.models.password_reset import PasswordResetToken
from app.models.revoked_token import RevokedToken
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    Token,
    UserOut,
)
from app.services import audit
from app.services.notifications import get_channel

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_predates_epoch(claims: dict, user: User) -> bool:
    """True if this token was issued (iat) before the user's current session
    epoch (User.sessions_valid_from) -- i.e. it was minted before the most
    recent password reset and must be rejected even though it isn't
    individually revoked.

    jose's encoder converts a datetime `iat` via `timegm(dt.utctimetuple())`,
    which floors to whole seconds -- so a token minted a few hundred ms after
    the epoch can carry an `iat` that floors to a second *before* the epoch's
    microsecond-precision timestamp. Flooring the epoch to the same
    granularity before comparing avoids rejecting a token that is, in real
    wall-clock terms, not actually stale.
    """
    iat = claims.get("iat")
    if iat is None:
        return True
    issued_at = datetime.fromtimestamp(iat, tz=UTC).replace(tzinfo=None)
    epoch = user.sessions_valid_from.replace(microsecond=0)
    return issued_at < epoch

# Generic response for forgot-password regardless of outcome, so the endpoint
# cannot be used to enumerate registered email addresses.
_FORGOT_PASSWORD_ACK = {
    "message": "If that email is registered, a password reset link has been sent."
}


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH
    )


def _issue_pair(response: Response, user: User) -> Token:
    access = create_access_token(subject=user.email, role=user.role, tourist_id=user.tourist_id)
    refresh, _jti, _exp = create_refresh_token(
        subject=user.email, role=user.role, tourist_id=user.tourist_id
    )
    _set_refresh_cookie(response, refresh)
    # The body still carries refresh_token for one release: existing/mobile
    # clients that store it themselves keep working, while the frontend now
    # relies on the cookie and never reads this field. See RefreshRequest.
    return Token(
        access_token=access, refresh_token=refresh, role=user.role,
        tourist_id=user.tourist_id, full_name=user.full_name,
    )


@router.post("/login", response_model=Token, dependencies=[Depends(login_rate_limit)])
def login(request: Request, response: Response, form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):
    """OAuth2 password flow — `username` field carries the email."""
    user = db.query(User).filter(User.email == form.username).first()
    # Constant-ish response: same error whether the email exists or not.
    if not user or not verify_password(form.password, user.hashed_password):
        audit.record(db, "login", actor=form.username or "unknown",
                     outcome="failure", request=request, detail="bad credentials")
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    audit.record(db, "login", actor=user.email, outcome="success", request=request)
    return _issue_pair(response, user)


@router.post("/refresh", response_model=Token)
def refresh(request: Request, response: Response,
            payload: RefreshRequest | None = None, db: Session = Depends(get_db)):
    """Trade a refresh token for a new access+refresh pair.

    The token comes from the httpOnly cookie if present, falling back to the
    request body for one release (see RefreshRequest). Refresh tokens are
    rotated on every use (the presented one is revoked and a new one issued)
    rather than reused: if a refresh token is ever stolen, the legitimate
    client's next refresh attempt will fail because the token it's holding
    was already consumed, which is a detectable signal of theft that reusing
    the same refresh token indefinitely would not give you.
    """
    token = request.cookies.get(settings.REFRESH_COOKIE_NAME) or (payload.refresh_token if payload else None)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    claims = decode_refresh_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    jti = claims.get("jti")
    if jti and db.get(RevokedToken, jti) is not None:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    user = db.query(User).filter(User.email == claims["sub"]).first()
    if not user or _token_predates_epoch(claims, user):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if jti:
        exp = datetime.fromtimestamp(claims["exp"], tz=UTC).replace(tzinfo=None)
        db.add(RevokedToken(jti=jti, expires_at=exp))
        db.commit()

    return _issue_pair(response, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response,
           payload: LogoutRequest | None = None, db: Session = Depends(get_db)):
    """Revoke a refresh token so it can no longer mint new access tokens.
    Any access token already issued keeps working until it naturally expires
    (up to ACCESS_TOKEN_EXPIRE_MINUTES) -- that's the trade-off of not
    checking a denylist on every single request."""
    _clear_refresh_cookie(response)
    token = request.cookies.get(settings.REFRESH_COOKIE_NAME) or (payload.refresh_token if payload else None)
    if not token:
        return  # nothing to revoke, no error either
    claims = decode_refresh_token(token)
    if not claims:
        return  # already invalid/expired: nothing to revoke, no error either
    jti = claims.get("jti")
    if jti and db.get(RevokedToken, jti) is None:
        exp = datetime.fromtimestamp(claims["exp"], tz=UTC).replace(tzinfo=None)
        db.add(RevokedToken(jti=jti, expires_at=exp))
        db.commit()


@router.post("/forgot-password", dependencies=[Depends(login_rate_limit)])
def forgot_password(payload: ForgotPasswordRequest, request: Request,
                    db: Session = Depends(get_db)):
    """Always returns the same generic acknowledgement -- an attacker probing
    for registered emails learns nothing from the response either way, and
    the same login rate limit that guards brute-force attempts also caps
    how many reset emails one client can trigger."""
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        db.add(PasswordResetToken(
            token_hash=token_hash, user_id=user.id,
            expires_at=utc_now() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        ))
        db.commit()
        get_channel().send(
            to=user.email,
            subject="Password reset request",
            body=(
                f"Use this code to reset your password (valid "
                f"{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes): {raw_token}"
            ),
        )
        audit.record(db, "forgot_password", actor=user.email, request=request)
    return _FORGOT_PASSWORD_ACK


@router.post("/reset-password", status_code=204)
def reset_password(payload: ResetPasswordRequest, request: Request,
                   db: Session = Depends(get_db)):
    """Resetting the password also bumps the user's session epoch
    (sessions_valid_from), so every access/refresh token issued before this
    moment is rejected on next use -- not just on its natural expiry. See
    _token_predates_epoch, used by both refresh() and deps.get_current_user.
    """
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash
    ).first()

    if (
        record is None
        or record.used_at is not None
        or record.expires_at < utc_now()
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user.hashed_password = hash_password(payload.new_password)
    user.sessions_valid_from = utc_now()
    record.used_at = utc_now()
    audit.record(db, "reset_password", actor=user.email, request=request)
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


def purge_expired_revocations(db: Session) -> int:
    """Drop revoked-token rows whose underlying token would have expired
    naturally anyway -- keeps the table from growing forever. Wired to the
    scheduler as the token_purge tick (see app/main.py)."""
    deleted = db.query(RevokedToken).filter(RevokedToken.expires_at < utc_now()).delete()
    db.commit()
    return deleted
