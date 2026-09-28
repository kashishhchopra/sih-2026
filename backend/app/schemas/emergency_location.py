"""Schemas for SOS live-location sharing (app/api/emergency.py)."""
from datetime import datetime

from pydantic import BaseModel, Field


class EmergencyLocationUpdate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy_m: float | None = Field(None, ge=0)
    speed_kmh: float | None = Field(None, ge=0)
    heading_deg: float | None = Field(None, ge=0, lt=360)


class EmergencyLocationPingOut(BaseModel):
    lat: float
    lng: float
    accuracy_m: float | None
    speed_kmh: float | None
    heading_deg: float | None
    timestamp: datetime
    anomaly_flag: bool
    demo: bool

    class Config:
        from_attributes = True


class EmergencyContactOut(BaseModel):
    name: str = ""
    phone: str = ""
    relation: str = ""


class EmergencyTrackOut(BaseModel):
    """Everything the police live map needs for one active emergency --
    including full tourist/case detail, so a station a case is transferred
    to has everything in this one call (see services/police_network.py's
    send_case)."""
    incident_id: int
    tourist_id: int
    tourist_name: str
    digital_id: str
    tourist_phone: str | None = None
    tourist_nationality: str | None = None
    tourist_photo: str | None = None
    safety_score: float | None = None
    hotel: str | None = None
    emergency_contacts: list[EmergencyContactOut] = []
    incident_type: str
    severity: str
    status: str
    description: str = ""
    detected_at: datetime | None = None
    live_tracking_active: bool
    station_id: int | None
    station_name: str | None
    # live | stale | offline | no_data -- see services/emergency_location.py
    location_status: str
    seconds_since_update: float | None
    latest: EmergencyLocationPingOut | None
    trail: list[EmergencyLocationPingOut]
    # Set while a transfer request to another station is awaiting
    # accept/reject -- see services/police_network.py's request/accept/
    # reject_transfer. The live-location feed above continues unaffected
    # either way.
    pending_transfer_id: int | None = None
    pending_transfer_to_station_id: int | None = None
