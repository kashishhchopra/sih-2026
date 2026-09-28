from datetime import datetime

from pydantic import BaseModel


class DisasterAdvisoryOut(BaseModel):
    id: int
    zone_id: int
    hazard_type: str
    severity: str
    message: str
    source: str
    active: bool
    issued_at: datetime
    expires_at: datetime | None
    # Added for the Disaster & Weather Alert Feed system -- nullable so
    # advisories created before this existed still serialize cleanly.
    title: str | None = None
    instructions: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    zone_name: str | None = None
    area_desc: str | None = None

    class Config:
        from_attributes = True


class DisasterAdvisoryWithImpact(DisasterAdvisoryOut):
    """DisasterAdvisoryOut plus how many tourists are currently inside the
    affected zone -- the Police Network Dashboard's "Disaster & Weather
    Monitoring" section. See app/api/police_network.py::disaster_summary."""
    affected_tourists: int
    station_id: int | None = None
    station_name: str | None = None
