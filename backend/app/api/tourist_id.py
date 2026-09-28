"""Digital Tourist Safety ID: the card, its QR/token lifecycle, authorized
scanning (QR or manual ID), and the scan audit trail.

See services/tourist_id.py for the actual verification/authorization logic
this thinly wraps.
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import (
    require_admin,
    require_admin_or_responder,
    require_scan_authorized,
    require_self_admin_or_responder,
    require_self_or_admin,
)
from app.db.session import get_db
from app.models.incident import Incident, IncidentEvent
from app.models.tourist import Tourist
from app.models.tourist_id import TouristIdScan
from app.models.user import User
from app.schemas.tourist_id import (
    DigitalIdCardOut,
    MyScanOut,
    PhotoUpdate,
    ReportIncidentFromScan,
    ScanRequest,
    TouristIdScanOut,
)
from app.services import audit, police_network
from app.services import tourist_id as tourist_id_service

router = APIRouter(tags=["tourist-id"])


def _get_tourist_or_404(tourist_id: int, db: Session) -> Tourist:
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return t


@router.get("/tourists/{tourist_id}/digital-id", response_model=DigitalIdCardOut)
def get_digital_id(tourist_id: int, db: Session = Depends(get_db),
                   _: User = Depends(require_self_admin_or_responder)):
    """The tourist's own Digital Safety ID card -- photo, status, and (only
    right after issuance/regeneration) the QR image. A card fetched later
    still returns everything except a fresh `qr_png_base64`, since the raw
    token is never stored and so cannot be re-rendered without regenerating."""
    t = _get_tourist_or_404(tourist_id, db)
    return tourist_id_service.digital_id_card(db, t)


@router.post("/tourists/{tourist_id}/digital-id/regenerate", response_model=DigitalIdCardOut)
def regenerate_digital_id(tourist_id: int, db: Session = Depends(get_db),
                          _: User = Depends(require_self_or_admin)):
    """Invalidate the current QR token and issue a new one. The old QR image
    stops verifying immediately -- see services/tourist_id.py:regenerate_token."""
    t = _get_tourist_or_404(tourist_id, db)
    return tourist_id_service.regenerate_card(db, t)


@router.post("/tourists/{tourist_id}/digital-id/suspend", status_code=204)
def suspend_digital_id(tourist_id: int, db: Session = Depends(get_db),
                       _: User = Depends(require_admin)):
    """Administrative suspension: invalidates the current token with no
    replacement. The ID shows "invalidated" on scan until reactivated."""
    t = _get_tourist_or_404(tourist_id, db)
    tourist_id_service.suspend(db, t)
    db.commit()


@router.post("/tourists/{tourist_id}/digital-id/reactivate", response_model=DigitalIdCardOut)
def reactivate_digital_id(tourist_id: int, db: Session = Depends(get_db),
                          _: User = Depends(require_admin)):
    t = _get_tourist_or_404(tourist_id, db)
    return tourist_id_service.regenerate_card(db, t)


@router.patch("/tourists/{tourist_id}/photo", status_code=204)
def update_photo(tourist_id: int, payload: PhotoUpdate, db: Session = Depends(get_db),
                 _: User = Depends(require_self_or_admin)):
    t = _get_tourist_or_404(tourist_id, db)
    t.photo = payload.photo
    db.commit()


@router.get("/tourists/{tourist_id}/id-scans", response_model=list[TouristIdScanOut])
def list_id_scans(tourist_id: int, limit: int = 50, db: Session = Depends(get_db),
                  _: User = Depends(require_self_admin_or_responder)):
    """Who has scanned this tourist's Digital ID -- a tourist can see their
    own scan history; admins/responders can look up anyone's."""
    _get_tourist_or_404(tourist_id, db)
    rows = (
        db.query(TouristIdScan)
        .filter(TouristIdScan.tourist_id == tourist_id)
        .order_by(TouristIdScan.scanned_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": r.id, "tourist_id": r.tourist_id, "scanner_role": r.scanner_role,
            "method": r.method, "scanned_at": r.scanned_at,
            "verification_status": r.verification_status,
            "accessed_fields": json.loads(r.accessed_fields or "[]"),
        }
        for r in rows
    ]


@router.post("/tourist-id/scan")
def scan_tourist_id(payload: ScanRequest, db: Session = Depends(get_db),
                    user: User = Depends(require_scan_authorized)):
    """The single entry point for both QR scans and manual Tourist Safety ID
    lookups -- see services/tourist_id.py:scan(). Returns a role-filtered
    view of the tourist on success, or a clear verification_status/reason on
    failure (not_found / invalidated / expired). Every attempt is audited,
    successful or not."""
    if not payload.token and not payload.digital_id:
        raise HTTPException(status_code=400, detail="Provide either a token or a digital_id")
    return tourist_id_service.scan(
        db, user, token_raw=payload.token, digital_id=payload.digital_id,
        lat=payload.lat, lng=payload.lng,
    )


@router.get("/tourist-id/scans/mine", response_model=list[MyScanOut])
def my_recent_scans(limit: int = 10, db: Session = Depends(get_db),
                    user: User = Depends(require_scan_authorized)):
    """The requesting account's own recent verifications."""
    return tourist_id_service.my_recent_scans(db, user, limit)


@router.post("/tourist-id/report-incident", status_code=201)
def report_incident_from_scan(payload: ReportIncidentFromScan, request: Request,
                              db: Session = Depends(get_db),
                              user: User = Depends(require_admin_or_responder)):
    """File an incident straight from a verified Digital ID scan -- takes
    the tourist's public Tourist Safety ID, never the internal numeric id
    (which a scan result never exposes). Routes through the same
    zone -> station assignment every other incident gets."""
    t = db.query(Tourist).filter(Tourist.digital_id == payload.digital_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")

    inc = Incident(
        tourist_id=t.id, type="field_report", severity=payload.severity, status="detected",
        description=payload.description, lat=t.last_lat, lng=t.last_lng,
    )
    db.add(inc)
    db.flush()
    db.add(IncidentEvent(
        incident_id=inc.id, status="detected",
        note=f"Filed by {user.email} from a Digital Tourist ID scan: {payload.description}",
    ))
    station = police_network.assign_station(db, inc)
    db.commit()
    audit.record(db, "incident_from_scan", actor=user.email, target=t.digital_id,
                detail=payload.description, request=request)
    return {"incident_id": inc.id, "status": inc.status, "station_id": station.id if station else None}
