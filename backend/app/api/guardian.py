"""Trip Guardian (Family Live-Share).

Management endpoints (create/list/revoke a share) require the tourist's own
login, same as the rest of their data. The resolve endpoint is deliberately
public and unauthenticated -- a guardian has no account, only the link the
tourist handed them -- so it exposes nothing beyond what that one read-only
share link is scoped to (this tourist's live status), and never the tourist's
document number, phone, or full profile.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_self_or_admin
from app.db.session import get_db
from app.models.guardian import TripGuardian
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.guardian import TripGuardianCreate, TripGuardianOut

router = APIRouter(tags=["guardian"])


@router.post("/tourists/{tourist_id}/guardians", response_model=TripGuardianOut, status_code=201)
def create_guardian(tourist_id: int, payload: TripGuardianCreate, db: Session = Depends(get_db),
                    _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    guardian = TripGuardian(
        tourist_id=tourist_id, guardian_name=payload.guardian_name,
        guardian_contact=payload.guardian_contact,
    )
    db.add(guardian)
    db.commit()
    db.refresh(guardian)
    return guardian


@router.get("/tourists/{tourist_id}/guardians", response_model=list[TripGuardianOut])
def list_guardians(tourist_id: int, db: Session = Depends(get_db),
                   _: User = Depends(require_self_or_admin)):
    return (
        db.query(TripGuardian)
        .filter(TripGuardian.tourist_id == tourist_id)
        .order_by(TripGuardian.created_at.desc())
        .all()
    )


@router.post("/tourists/{tourist_id}/guardians/{guardian_id}/revoke", response_model=TripGuardianOut)
def revoke_guardian(tourist_id: int, guardian_id: int, db: Session = Depends(get_db),
                    _: User = Depends(require_self_or_admin)):
    guardian = (
        db.query(TripGuardian)
        .filter(TripGuardian.id == guardian_id, TripGuardian.tourist_id == tourist_id)
        .first()
    )
    if not guardian:
        raise HTTPException(status_code=404, detail="Guardian share not found")
    guardian.revoked = True
    db.commit()
    db.refresh(guardian)
    return guardian


@router.get("/guardian/{token}")
def resolve_guardian_link(token: str, db: Session = Depends(get_db)):
    """Public, unauthenticated: what the family member's browser polls. No
    login -- the token itself is the credential, same trust model as a
    calendar share link or a password-reset link."""
    guardian = db.query(TripGuardian).filter(TripGuardian.token == token).first()
    if not guardian or guardian.revoked:
        raise HTTPException(status_code=404, detail="This share link is invalid or has been revoked")
    t = db.get(Tourist, guardian.tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="This share link is invalid or has been revoked")
    return {
        "guardian_name": guardian.guardian_name,
        "tourist_name": t.full_name,
        "status": t.status,
        "safety_score": t.safety_score,
        "last_lat": t.last_lat,
        "last_lng": t.last_lng,
        "last_seen": t.last_seen,
        "trip_start": t.trip_start,
        "trip_end": t.trip_end,
        "trip_active": t.is_valid,
    }
