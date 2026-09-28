"""Thin, authenticated read-only endpoint over services/maps.py -- lets the
frontend re-resolve a single place name on demand (e.g. the itinerary
review screen's "Locate" button for a destination the automatic parse
couldn't place), without duplicating the geocoding logic client-side.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.services import maps

router = APIRouter(prefix="/maps", tags=["maps"])


@router.get("/geocode")
def geocode_place(place: str, _: User = Depends(get_current_user)):
    """Resolve a place name to coordinates. Returns `{lat, lng, demo}` on a
    match, or `{lat: null, lng: null}` if the place can't be resolved --
    never a guessed location."""
    result = maps.geocode(place)
    if result is None:
        return {"lat": None, "lng": None, "demo": True}
    return result
