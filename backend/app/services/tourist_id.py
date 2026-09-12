"""Digital Tourist Safety ID: secure QR token lifecycle, verification, and
role-based scan authorization.

    QR code  ->  raw token (never stored)  ->  SHA-256 hash lookup  ->
    TouristIdToken  ->  tourist  ->  role-filtered permitted view

The QR/manual-lookup payload is deliberately minimal -- just the token or the
public-ish Tourist Safety ID (`Tourist.digital_id`), never the tourist's full
record. Everything a scanner is allowed to see comes back only after the
backend verifies the token and looks up the *scanner's* role -- see
`permitted_view`. This is the same "store only a hash, verify server-side"
pattern already used for password-reset tokens (app/models/password_reset.py).
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
from datetime import timedelta

import qrcode
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models.incident import Incident
from app.models.tourist import Tourist
from app.models.tourist_id import TouristIdScan, TouristIdToken
from app.models.user import User
from app.services import audit, police_network

# Roles authorized to scan/verify a Digital Tourist Safety ID at all. Each
# gets a different *view* of the same verified tourist -- see permitted_view.
SCAN_AUTHORIZED_ROLES = ("admin", "responder")


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _qr_data_uri(raw_token: str) -> str:
    # "TSID:" prefix makes a raw scan of the QR (e.g. by an unrelated app)
    # self-describing without adding any tourist information to the payload.
    img = qrcode.make(f"TSID:{raw_token}")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"


def issue_token(db: Session, tourist: Tourist) -> tuple[TouristIdToken, str]:
    """Mint a new active token for a tourist. Does not touch any existing
    token -- callers that mean to replace one should call regenerate_token."""
    raw = secrets.token_urlsafe(24)
    row = TouristIdToken(
        tourist_id=tourist.id, token_hash=_hash(raw), raw_token_encrypted=raw, status="active",
    )
    db.add(row)
    db.flush()
    return row, raw


def _current_token(db: Session, tourist_id: int) -> TouristIdToken | None:
    return (
        db.query(TouristIdToken)
        .filter(TouristIdToken.tourist_id == tourist_id, TouristIdToken.status == "active")
        .order_by(TouristIdToken.issued_at.desc())
        .first()
    )


def regenerate_token(db: Session, tourist: Tourist) -> tuple[TouristIdToken, str]:
    """Invalidate every active token for this tourist and issue a fresh one.
    The old QR image immediately stops verifying."""
    now = utc_now()
    (
        db.query(TouristIdToken)
        .filter(TouristIdToken.tourist_id == tourist.id, TouristIdToken.status == "active")
        .update({"status": "invalidated", "invalidated_at": now})
    )
    return issue_token(db, tourist)


def suspend(db: Session, tourist: Tourist) -> None:
    """Administratively invalidate the current token with no replacement --
    the ID stops verifying (shows "invalidated") until reactivate() is called."""
    now = utc_now()
    (
        db.query(TouristIdToken)
        .filter(TouristIdToken.tourist_id == tourist.id, TouristIdToken.status == "active")
        .update({"status": "invalidated", "invalidated_at": now})
    )


def id_status(tourist: Tourist, token: TouristIdToken | None) -> str:
    """active / expiring_soon / expired / invalidated -- backend-computed,
    not a frontend label. See settings.ID_EXPIRING_SOON_HOURS."""
    if token is None or token.status != "active":
        return "invalidated"
    now = utc_now()
    if now > tourist.trip_end:
        return "expired"
    if tourist.trip_end - now <= timedelta(hours=settings.ID_EXPIRING_SOON_HOURS):
        return "expiring_soon"
    if now < tourist.trip_start:
        return "expiring_soon"  # not yet active, but not worth its own state for a demo
    return "active"


def digital_id_card(db: Session, tourist: Tourist) -> dict:
    """The tourist's own view of their Digital Safety ID card: photo, QR,
    status. Auto-issues a token if this tourist predates the feature. The QR
    is re-rendered from the encrypted raw token every time -- the owner can
    reopen their card any time without that alone invalidating it (only an
    explicit regenerate/suspend does)."""
    token = _current_token(db, tourist.id)
    if token is None:
        token, _raw = issue_token(db, tourist)
        db.commit()
    status = id_status(tourist, token)
    return {
        "digital_id": tourist.digital_id,
        "full_name": tourist.full_name,
        "photo": tourist.photo,
        "hotel": tourist.hotel,
        "trip_start": tourist.trip_start,
        "trip_end": tourist.trip_end,
        "id_status": status,
        "issued_at": token.issued_at,
        "qr_png_base64": _qr_data_uri(token.raw_token_encrypted),
    }


def regenerate_card(db: Session, tourist: Tourist) -> dict:
    token, raw = regenerate_token(db, tourist)
    db.commit()
    return {
        "digital_id": tourist.digital_id,
        "full_name": tourist.full_name,
        "photo": tourist.photo,
        "hotel": tourist.hotel,
        "trip_start": tourist.trip_start,
        "trip_end": tourist.trip_end,
        "id_status": id_status(tourist, token),
        "issued_at": token.issued_at,
        "qr_png_base64": _qr_data_uri(raw),
    }


def _lookup(db: Session, token_raw: str | None, digital_id: str | None) -> tuple[Tourist | None, TouristIdToken | None, str]:
    """Resolve a scan target. Returns (tourist, token_row, method)."""
    if token_raw:
        payload = token_raw[5:] if token_raw.startswith("TSID:") else token_raw
        row = db.query(TouristIdToken).filter(TouristIdToken.token_hash == _hash(payload)).first()
        if row is None:
            return None, None, "qr_token"
        return db.get(Tourist, row.tourist_id), row, "qr_token"
    if digital_id:
        t = db.query(Tourist).filter(Tourist.digital_id == digital_id.strip()).first()
        return t, (_current_token(db, t.id) if t else None), "manual_id"
    return None, None, "manual_id"


def _permitted_view(db: Session, tourist: Tourist, role: str) -> dict:  # noqa: ARG001
    """Role-filtered fields for a *verified* tourist. This is the actual
    authorization boundary -- enforced here, server-side, not by the frontend
    choosing what to render. Currently every SCAN_AUTHORIZED_ROLES member
    (admin/responder) gets the same "police tier" view; `role` is kept as a
    parameter so a more restricted tier (e.g. hotel) can be reintroduced here
    without changing every call site."""
    base = {
        "digital_id": tourist.digital_id,
        "full_name": tourist.full_name,
        "photo": tourist.photo,
    }

    zone = None
    station = None
    if tourist.last_lat is not None and tourist.last_lng is not None:
        z = police_network.resolve_zone_for_point(db, tourist.last_lat, tourist.last_lng)
        if z:
            zone = {"id": z.id, "name": z.name, "risk_level": z.risk_level}
            st = police_network.station_for_zone(db, z.id)
            if st:
                station = {"id": st.id, "name": st.name, "phone": st.phone}
    open_incidents = (
        db.query(Incident)
        .filter(Incident.tourist_id == tourist.id, Incident.status != "resolved")
        .order_by(Incident.detected_at.desc())
        .all()
    )
    base.update({
        "hotel": tourist.hotel,
        "trip_start": tourist.trip_start,
        "trip_end": tourist.trip_end,
        "trip_status": tourist.status,
        "safety_score": tourist.safety_score,
        "last_lat": tourist.last_lat,
        "last_lng": tourist.last_lng,
        "last_seen": tourist.last_seen,
        "current_zone": zone,
        "assigned_station": station,
        "emergency_contacts": json.loads(tourist.emergency_contacts or "[]"),
        "active_incidents": [
            {"id": i.id, "type": i.type, "severity": i.severity, "status": i.status}
            for i in open_incidents
        ],
    })
    return base


def scan(
    db: Session, scanner: User, token_raw: str | None = None, digital_id: str | None = None,
    lat: float | None = None, lng: float | None = None,
) -> dict:
    """The single authorized entry point for both QR scans and manual
    lookups. Always writes an audit trail row, whether verification
    succeeds or not -- a failed/unauthorized attempt is exactly the kind of
    thing an audit log exists to catch.
    """
    tourist, token, method = _lookup(db, token_raw, digital_id)

    if tourist is None:
        result = {"verification_status": "not_found", "reason": "No tourist matches that ID or QR code."}
        _record_scan(db, None, scanner, method, "not_found", [], lat, lng)
        return result

    status = id_status(tourist, token)
    if status == "invalidated":
        result = {
            "verification_status": "invalidated",
            "reason": "This QR code has been regenerated or suspended and is no longer valid.",
            "digital_id": tourist.digital_id, "full_name": tourist.full_name,
        }
        _record_scan(db, tourist, scanner, method, "invalidated", [], lat, lng)
        return result
    if status == "expired":
        result = {
            "verification_status": "expired",
            "reason": "This tourist's trip has ended; the Digital ID is no longer active.",
            "digital_id": tourist.digital_id, "full_name": tourist.full_name,
        }
        _record_scan(db, tourist, scanner, method, "expired", [], lat, lng)
        return result

    view = _permitted_view(db, tourist, scanner.role)
    view["verification_status"] = "verified"
    view["id_status"] = status
    _record_scan(db, tourist, scanner, method, "verified", list(view.keys()), lat, lng)
    return view


def _record_scan(
    db: Session, tourist: Tourist | None, scanner: User, method: str, verification_status: str,
    accessed_fields: list[str], lat: float | None, lng: float | None,
) -> None:
    db.add(TouristIdScan(
        tourist_id=tourist.id if tourist else None,
        scanner_user_id=scanner.id, scanner_role=scanner.role, method=method,
        scan_lat=lat, scan_lng=lng, verification_status=verification_status,
        accessed_fields=json.dumps(accessed_fields),
    ))
    db.commit()
    audit.record(
        action="qr_scan", actor=scanner.email,
        target=tourist.digital_id if tourist else (method or "unknown"),
        detail=json.dumps({
            "scanner_role": scanner.role, "method": method,
            "accessed_fields": accessed_fields,
        }),
        outcome=verification_status,
    )


def my_recent_scans(db: Session, user: User, limit: int = 10) -> list[dict]:
    """The requesting account's own scan history. Deliberately re-derived
    from the same scan rows every account's scans already write to, not a
    separate log."""
    rows = (
        db.query(TouristIdScan)
        .filter(TouristIdScan.scanner_user_id == user.id)
        .order_by(TouristIdScan.scanned_at.desc())
        .limit(min(limit, 50))
        .all()
    )
    tourist_ids = {r.tourist_id for r in rows if r.tourist_id}
    tourists = {t.id: t for t in db.query(Tourist).filter(Tourist.id.in_(tourist_ids)).all()} if tourist_ids else {}
    out = []
    for r in rows:
        t = tourists.get(r.tourist_id)
        out.append({
            "id": r.id, "scanned_at": r.scanned_at, "verification_status": r.verification_status,
            "digital_id": t.digital_id if t else None, "full_name": t.full_name if t else None,
        })
    return out
