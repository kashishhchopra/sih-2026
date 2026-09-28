"""External Hash-Chain Anchoring. See services/anchoring.py."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.anchor import ChainAnchor
from app.models.user import User
from app.schemas.anchor import ChainAnchorOut
from app.services import anchoring

router = APIRouter(prefix="/anchors", tags=["anchoring"])


@router.get("", response_model=list[ChainAnchorOut])
def list_anchors(limit: int = 50, db: Session = Depends(get_db),
                 _: User = Depends(require_admin)):
    return (
        db.query(ChainAnchor)
        .order_by(ChainAnchor.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )


@router.post("", response_model=ChainAnchorOut, status_code=201)
def create_anchor(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Publish the current chain root right now, rather than waiting for the
    next scheduled tick -- useful for a demo."""
    return anchoring.publish_anchor(db)


@router.get("/{anchor_id}/verify")
def verify_anchor(anchor_id: int, db: Session = Depends(get_db),
                  _: User = Depends(require_admin)):
    anchor = db.get(ChainAnchor, anchor_id)
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    return {"anchor_id": anchor_id, **anchoring.verify_anchor(anchor)}
