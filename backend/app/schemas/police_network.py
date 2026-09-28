"""Schemas for the area-based police network endpoints (app/api/police_network.py)."""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.cctv import STREAM_TYPES


class PoliceStationOut(BaseModel):
    id: int
    name: str
    zone_id: int | None
    phone: str
    contact_officer: str
    lat: float
    lng: float

    class Config:
        from_attributes = True


class PoliceStationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    zone_id: int | None = None
    phone: str = "100"
    contact_officer: str = ""
    lat: float
    lng: float


class CameraOut(BaseModel):
    id: int
    label: str
    zone_id: int | None
    lat: float
    lng: float
    status: str
    distance_m: float | None = None
    # Optional real video feed. Null on a camera that is only a coverage
    # record -- see models/police.py::Camera and services/cctv.py.
    stream_url: str | None = None
    stream_type: str = "none"
    feed_source: str = "manual"
    assigned_station_id: int | None = None

    class Config:
        from_attributes = True


class CameraCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=200)
    zone_id: int | None = None
    lat: float
    lng: float
    status: str = "active"
    # How an operator onboards a camera that actually has a feed. Left unset
    # the camera stays a coverage-only directory entry, exactly as before.
    stream_url: str | None = Field(None, max_length=2000)
    stream_type: str | None = Field(None, max_length=16)
    feed_source: str = Field("manual", max_length=100)
    source_url: str | None = Field(None, max_length=2000)
    attribution: str | None = Field(None, max_length=300)
    assigned_station_id: int | None = None

    @field_validator("stream_type")
    @classmethod
    def _known_stream_type(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in STREAM_TYPES:
            raise ValueError(f"stream_type must be one of {', '.join(STREAM_TYPES)}")
        return v


class ForwardIncidentRequest(BaseModel):
    to_station_id: int
    note: str = Field("", max_length=1000)


class TransferRequestIn(BaseModel):
    to_station_id: int
    reason: str = Field("", max_length=1000)
    share_live_location: bool = True


class SendCaseIn(BaseModel):
    """Direct, one-click case hand-off -- see
    services/police_network.py:send_case. No accept/reject step: the case
    (and its live-location session) moves to `to_station_id` immediately."""
    to_station_id: int
    reason: str = Field("", max_length=1000)
    share_live_location: bool = True


class TransferRespondIn(BaseModel):
    reason: str = Field("", max_length=1000)


class TransferOut(BaseModel):
    id: int
    incident_id: int
    from_station_id: int | None
    to_station_id: int
    reason: str
    status: str
    requested_by: str
    responded_by: str | None
    location_shared: bool
    latest_lat: float | None
    latest_lng: float | None
    latest_location_at: datetime | None
    requested_at: datetime
    responded_at: datetime | None

    class Config:
        from_attributes = True


class StationDashboardEntry(BaseModel):
    id: int
    name: str
    phone: str
    contact_officer: str
    lat: float
    lng: float
    zone_id: int | None
    zone_name: str | None
    open_incidents: int
    critical_incidents: int
    incident_ids: list[int]
    total_officers: int
    max_concurrent_cases: int
    has_capacity: bool
    load_pct: float


class CentralDashboardOut(BaseModel):
    generated_at: datetime
    stations: list[StationDashboardEntry]
    unassigned_incidents: list[int]
    total_open_incidents: int


class StationCapacityOut(BaseModel):
    """Live resource status for one station -- Police Station Resource
    Fallback System (services/police_network.py)."""
    station_id: int
    name: str
    open_cases: int
    max_concurrent_cases: int
    total_officers: int
    has_capacity: bool
    load_pct: float


class StationFallbackOut(BaseModel):
    """One entry in the ranked fallback order for a location."""
    station_id: int
    name: str
    distance_km: float
    open_cases: int
    max_concurrent_cases: int
    total_officers: int
    has_capacity: bool
    load_pct: float
