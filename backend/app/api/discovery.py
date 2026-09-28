"""Discovery API: hidden spots, regional food, homestays -- and an offline
bundle for low-connectivity caching. See services/discovery.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.discovery import DiscoveryResponse, OfflineBundle
from app.services import discovery

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("", response_model=DiscoveryResponse)
def get_discovery(
    lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(25.0, gt=0, le=100),
    categories: str | None = Query(None, description="Comma-separated: hidden_gem,regional_food,homestay"),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    return {
        "lat": lat, "lng": lng, "radius_km": radius_km,
        "places": discovery.find_discovery(db, lat, lng, radius_km, cat_list),
    }


@router.get("/offline-bundle", response_model=OfflineBundle)
def get_offline_bundle(
    lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(25.0, gt=0, le=100),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    return discovery.offline_bundle(db, lat, lng, radius_km)
