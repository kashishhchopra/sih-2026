"""Fair Price API: fare estimation + reporting for local transport. See
services/fare.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_self_or_admin
from app.core.time import utc_now
from app.db.session import get_db
from app.models.fare_check import FareCheck
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.fare import FareCheckOut, FareCheckRequest, FareReportRequest
from app.services import fare as fare_service

router = APIRouter(tags=["fare"])


@router.get("/fare/transport-types")
def list_transport_types():
    return fare_service.TRANSPORT_TYPES


@router.post("/tourists/{tourist_id}/fare-checks", response_model=FareCheckOut, status_code=201)
def create_fare_check(
    tourist_id: int, payload: FareCheckRequest,
    db: Session = Depends(get_db), _: User = Depends(require_self_or_admin),
):
    if not db.get(Tourist, tourist_id):
        raise HTTPException(status_code=404, detail="Tourist not found")
    if payload.transport_type not in fare_service.TRANSPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown transport type: {payload.transport_type}")

    result = fare_service.check_fare(
        payload.transport_type, payload.pickup_lat, payload.pickup_lng,
        payload.destination_lat, payload.destination_lng, payload.quoted_fare,
    )
    check = FareCheck(
        tourist_id=tourist_id, transport_type=payload.transport_type,
        pickup_name=payload.pickup_name, pickup_lat=payload.pickup_lat, pickup_lng=payload.pickup_lng,
        destination_name=payload.destination_name, destination_lat=payload.destination_lat,
        destination_lng=payload.destination_lng,
        distance_km=result["distance_km"], duration_min=result["duration_min"],
        estimated_min=result["estimated_min"], estimated_max=result["estimated_max"],
        quoted_fare=payload.quoted_fare, verdict=result["verdict"], percent_diff=result["percent_over"],
    )
    db.add(check)
    db.commit()
    db.refresh(check)
    return check


@router.get("/tourists/{tourist_id}/fare-checks", response_model=list[FareCheckOut])
def list_fare_checks(tourist_id: int, db: Session = Depends(get_db),
                     _: User = Depends(require_self_or_admin)):
    return (
        db.query(FareCheck).filter(FareCheck.tourist_id == tourist_id)
        .order_by(FareCheck.created_at.desc()).all()
    )


def _get_own_check_or_404(tourist_id: int, check_id: int, db: Session) -> FareCheck:
    check = db.get(FareCheck, check_id)
    if check is None or check.tourist_id != tourist_id:
        raise HTTPException(status_code=404, detail="Fare check not found")
    return check


@router.post("/tourists/{tourist_id}/fare-checks/{check_id}/report", response_model=FareCheckOut)
def report_fare(
    tourist_id: int, check_id: int, payload: FareReportRequest,
    db: Session = Depends(get_db), _: User = Depends(require_self_or_admin),
):
    """The tourist flags a fare as unreasonable -- feeds the Government
    Dashboard's transport-complaint aggregation (app/api/government.py)."""
    check = _get_own_check_or_404(tourist_id, check_id, db)
    check.reported = True
    check.report_note = payload.note
    check.reported_at = utc_now()
    db.commit()
    db.refresh(check)
    return check
