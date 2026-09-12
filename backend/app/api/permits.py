"""Permit / E-Pass Automation API: pre-filled permit applications for a
tourist, generated from their own KYC + itinerary. See services/permit.py.

Two-step by design: create a draft (pre-filled, editable) -> the tourist
reviews/edits it -> confirm explicitly. Confirming never submits anything to
a government system (none is integrated) -- it hands back the real official
portal URL for the tourist to finish the actual submission themselves.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_self_or_admin
from app.db.session import get_db
from app.models.permit import Permit
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.permit import PermitCreateRequest, PermitFormUpdate, PermitOut, PermitTypeOut
from app.services import permit as permit_service

router = APIRouter(tags=["permits"])


@router.get("/permits/types", response_model=list[PermitTypeOut])
def list_permit_types():
    return permit_service.PERMIT_TYPES


@router.get("/tourists/{tourist_id}/permits", response_model=list[PermitOut])
def list_permits(tourist_id: int, db: Session = Depends(get_db), _: User = Depends(require_self_or_admin)):
    permits = db.query(Permit).filter(Permit.tourist_id == tourist_id).order_by(Permit.created_at.desc()).all()
    return [permit_service.serialize(p) for p in permits]


@router.post("/tourists/{tourist_id}/permits", response_model=PermitOut, status_code=201)
def start_permit_application(
    tourist_id: int, payload: PermitCreateRequest,
    db: Session = Depends(get_db), _: User = Depends(require_self_or_admin),
):
    """Step 1: create a pre-filled DRAFT. Nothing is submitted anywhere yet."""
    tourist = db.get(Tourist, tourist_id)
    if tourist is None:
        raise HTTPException(status_code=404, detail="Tourist not found")
    try:
        permit = permit_service.create_permit(
            db, tourist, payload.permit_type, payload.zone_id, payload.destination_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(permit)
    return permit_service.serialize(permit)


def _get_own_permit_or_404(tourist_id: int, permit_id: int, db: Session) -> Permit:
    permit = db.get(Permit, permit_id)
    if permit is None or permit.tourist_id != tourist_id:
        raise HTTPException(status_code=404, detail="Permit not found")
    return permit


@router.get("/tourists/{tourist_id}/permits/{permit_id}", response_model=PermitOut)
def get_permit(
    tourist_id: int, permit_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_self_or_admin),
):
    return permit_service.serialize(_get_own_permit_or_404(tourist_id, permit_id, db))


@router.patch("/tourists/{tourist_id}/permits/{permit_id}", response_model=PermitOut)
def edit_permit_draft(
    tourist_id: int, permit_id: int, payload: PermitFormUpdate, db: Session = Depends(get_db),
    _: User = Depends(require_self_or_admin),
):
    """The tourist corrects the pre-filled form before confirming."""
    permit = _get_own_permit_or_404(tourist_id, permit_id, db)
    try:
        permit_service.update_form(db, permit, payload.form)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(permit)
    return permit_service.serialize(permit)


@router.post("/tourists/{tourist_id}/permits/{permit_id}/confirm", response_model=PermitOut)
def confirm_permit(
    tourist_id: int, permit_id: int, db: Session = Depends(get_db),
    _: User = Depends(require_self_or_admin),
):
    """Step 2: explicit tourist confirmation, after reviewing the form.
    Returns the real official portal URL (`portal`) for the frontend to open
    in a new tab -- this endpoint itself never submits anything."""
    permit = _get_own_permit_or_404(tourist_id, permit_id, db)
    try:
        permit_service.confirm_and_get_portal(db, permit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(permit)
    return permit_service.serialize(permit)
