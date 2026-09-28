"""Crowd & Queue Forecast API. See services/crowd_forecast.py."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.crowd_forecast import QueueEstimate, ZoneCrowdForecast
from app.services import crowd_forecast

router = APIRouter(prefix="/crowd", tags=["crowd-forecast"])


@router.get("/forecast", response_model=list[ZoneCrowdForecast])
def get_crowd_forecast(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return crowd_forecast.forecast_zone_crowds(db)


@router.get("/forecast/poi/{poi_id}", response_model=QueueEstimate)
def get_poi_queue(poi_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    result = crowd_forecast.estimate_queue_wait(db, poi_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Point of interest not found")
    return result
