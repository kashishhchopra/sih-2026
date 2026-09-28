"""Schemas for the Smart Trip Planner (app/api/trip_planner.py)."""
from pydantic import BaseModel, Field


class TripPlanStop(BaseModel):
    name: str
    lat: float | None = None
    lng: float | None = None


class IndoorAlternative(BaseModel):
    name: str
    lat: float
    lng: float
    distance_km: float


class TripPlanFestival(BaseModel):
    id: int | str
    name: str
    description: str
    category: str
    next_start: str
    next_end: str
    crowd_impact: str
    distance_km: float | None = None
    source: str = "curated"


class TripPlanDay(BaseModel):
    day: int
    date: str | None = None
    stops: list[TripPlanStop] = Field(default_factory=list)
    weather_risk: float
    weather_band: str
    advisory: str
    indoor_alternative: IndoorAlternative | None = None
    festivals: list[TripPlanFestival] = Field(default_factory=list)
    permits_suggested: list[str] = Field(default_factory=list)


class TripPlanOut(BaseModel):
    tourist_id: int
    generated_at: str
    days: list[TripPlanDay] = Field(default_factory=list)
    replanning_suggested: bool = False
    notes: list[str] = Field(default_factory=list)
