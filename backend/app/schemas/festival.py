"""Schemas for Festival & Local Event Intelligence (app/api/festivals.py)."""
from pydantic import BaseModel


class FestivalOut(BaseModel):
    id: int | str
    name: str
    description: str
    category: str
    state: str | None
    lat: float | None
    lng: float | None
    next_start: str
    next_end: str
    crowd_impact: str
    distance_km: float | None = None
    # "curated" (this app's own festival calendar, app/models/festival.py) or
    # "public_holiday_api" (fetched live from Nager.Date, no key required).
    source: str = "curated"
