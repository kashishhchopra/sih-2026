"""Shared FastAPI dependencies: current user resolution & role guards."""
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Path, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, verify_password
from app.db.session import get_db
from app.models.device import Device
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_CREDS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_from_token(token: str, db: Session) -> User:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise _CREDS_EXC
    user = db.query(User).filter(User.email == payload["sub"]).first()
    if user is None:
        raise _CREDS_EXC
    # Reject a still-unexpired access token minted before the user's most
    # recent password reset. `User` is already loaded here, so this costs
    # zero extra queries and gives immediate global logout rather than
    # waiting for the access token to expire naturally. See
    # app/api/auth.py::_token_predates_epoch for the matching refresh-token
    # check and why the epoch is floored to whole seconds before comparing.
    iat = payload.get("iat")
    if iat is None:
        raise _CREDS_EXC
    issued_at = datetime.fromtimestamp(iat, tz=UTC).replace(tzinfo=None)
    if issued_at < user.sessions_valid_from.replace(microsecond=0):
        raise _CREDS_EXC
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    return _user_from_token(token, db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin/police access required")
    return user


def require_responder(user: User = Depends(get_current_user)) -> User:
    if user.role != "responder":
        raise HTTPException(status_code=403, detail="Responder access required")
    return user


def require_admin_or_responder(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "responder"):
        raise HTTPException(status_code=403, detail="Admin or responder access required")
    return user


def require_scan_authorized(user: User = Depends(get_current_user)) -> User:
    """Digital Tourist Safety ID: who may scan/verify a QR at all. Each
    authorized role still gets a different, role-filtered view of the
    verified tourist -- see services/tourist_id.py:_permitted_view. This
    dependency only gates "may attempt a scan", not "sees everything"."""
    from app.services.tourist_id import SCAN_AUTHORIZED_ROLES

    if user.role not in SCAN_AUTHORIZED_ROLES:
        raise HTTPException(status_code=403, detail="Not authorized to scan Tourist Safety IDs")
    return user


def require_self_or_admin(
    tourist_id: int = Path(...), user: User = Depends(get_current_user)
) -> User:
    """Allow admins, or a tourist acting only on their own record."""
    if user.role == "admin":
        return user
    if user.role == "tourist" and user.tourist_id == tourist_id:
        return user
    raise HTTPException(status_code=403, detail="Forbidden")


def require_self_admin_or_responder(
    tourist_id: int = Path(...), user: User = Depends(get_current_user)
) -> User:
    """Admins and responders (e.g. scanning a Digital Safety Passport in the
    field) see any tourist; a tourist may only act on their own record."""
    if user.role in ("admin", "responder"):
        return user
    if user.role == "tourist" and user.tourist_id == tourist_id:
        return user
    raise HTTPException(status_code=403, detail="Forbidden")


def authenticate_ws_token(token: str | None, db: Session) -> User | None:
    """Validate a token passed as a WebSocket query param. Returns None if invalid."""
    if not token:
        return None
    try:
        return _user_from_token(token, db)
    except HTTPException:
        return None


def authenticate_device(
    x_device_key: str = Header(..., alias="X-Device-Key"),
    device_id: str = Path(...),
    db: Session = Depends(get_db),
) -> Device:
    """Authenticate an IoT band by its per-device API key.

    A wearable cannot hold a user login session, so it authenticates with its
    own long-lived credential (hashed with the same bcrypt path as a user
    password) instead of a JWT.
    """
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device is None or not device.active or not verify_password(x_device_key, device.hashed_key):
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    return device
