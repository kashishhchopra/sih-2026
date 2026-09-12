"""Schemas for Crowd & Queue Forecast (app/api/crowd_forecast.py)."""
from pydantic import BaseModel, Field


class ZoneCrowdForecast(BaseModel):
    zone_id: int
    zone: str
    tourist_count: int
    current_density: str
    season: str
    is_holiday_period: bool
    holiday_name: str | None = None
    active_festivals: list[str] = Field(default_factory=list)
    forecast_density: str
    reasons: list[str] = Field(default_factory=list)


class QueueEstimate(BaseModel):
    poi_id: int
    name: str
    category: str
    estimated_wait_minutes: int
    band: str
