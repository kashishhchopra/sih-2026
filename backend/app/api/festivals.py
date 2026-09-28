"""Festival & Local Event Intelligence API: calendar of festivals/fairs/local
events, filterable and proximity-aware. See services/festival.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.festival import FestivalOut
from app.services import festival as festival_service

router = APIRouter(prefix="/festivals", tags=["festivals"])


@router.get("", response_model=list[FestivalOut])
def list_festivals(
    state: str | None = None, category: str | None = None,
    within_days: int | None = Query(None, ge=1, le=365),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    return festival_service.list_festivals(db, state=state, category=category, within_days=within_days)


@router.get("/near", response_model=list[FestivalOut])
def festivals_near(
    lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(150, gt=0, le=1000), within_days: int = Query(60, ge=1, le=365),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    return festival_service.upcoming_near(db, lat, lng, radius_km, within_days)
