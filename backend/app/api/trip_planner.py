"""Smart Trip Planner API: day-by-day plan generated from a tourist's
confirmed itinerary, with a pre-planning weather check per day. See
services/trip_planner.py.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_self_admin_or_responder
from app.db.session import get_db
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.trip_planner import TripPlanOut
from app.services.trip_planner import generate_trip_plan

router = APIRouter(prefix="/tourists/{tourist_id}", tags=["trip-planner"])


@router.get("/trip-plan", response_model=TripPlanOut)
def get_trip_plan(
    tourist_id: int, days: int | None = Query(None, ge=1, le=14),
    db: Session = Depends(get_db), _: User = Depends(require_self_admin_or_responder),
):
    tourist = db.get(Tourist, tourist_id)
    if tourist is None:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return generate_trip_plan(db, tourist, days)
