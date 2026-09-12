"""Schemas for Fair Price (app/api/fare.py)."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.tourist import LAT, LNG


class FareCheckRequest(BaseModel):
    transport_type: str = Field(..., min_length=1, max_length=32)
    pickup_name: str = Field("", max_length=120)
    pickup_lat: float = LAT
    pickup_lng: float = LNG
    destination_name: str = Field("", max_length=120)
    destination_lat: float = LAT
    destination_lng: float = LNG
    quoted_fare: float = Field(..., gt=0, le=100_000)


class FareReportRequest(BaseModel):
    note: str = Field("", max_length=500)


class FareCheckOut(BaseModel):
    id: int
    tourist_id: int
    transport_type: str
    pickup_name: str
    destination_name: str
    distance_km: float
    duration_min: float
    estimated_min: float
    estimated_max: float
    quoted_fare: float
    verdict: str
    percent_diff: float
    reported: bool
    report_note: str
    created_at: datetime
