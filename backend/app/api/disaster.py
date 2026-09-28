"""Disaster & Weather Alert Feeds. See services/disaster.py."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_self_or_admin
from app.db.session import get_db
from app.models.disaster import DisasterAdvisory
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.disaster import DisasterAdvisoryOut
from app.services import disaster

router = APIRouter(tags=["disaster"])


@router.get("/disasters", response_model=list[DisasterAdvisoryOut])
def list_disasters(active_only: bool = True, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    q = db.query(DisasterAdvisory)
    if active_only:
        q = q.filter(DisasterAdvisory.active.is_(True))
    return q.order_by(DisasterAdvisory.issued_at.desc()).all()


@router.get("/tourists/{tourist_id}/disasters", response_model=list[DisasterAdvisoryOut])
def tourist_disasters(tourist_id: int, db: Session = Depends(get_db),
                      _: User = Depends(require_self_or_admin)):
    """Active hazard advisories for whatever zone this tourist is currently in."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return disaster.active_advisories_for_tourist(db, t)
