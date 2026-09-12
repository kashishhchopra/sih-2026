from datetime import datetime

from pydantic import BaseModel, Field


class DeviceRegister(BaseModel):
    tourist_id: int
    device_id: str = Field(..., min_length=4, max_length=64)
    firmware_version: str = Field("1.0.0", max_length=20)


class DeviceRegistered(BaseModel):
    """Returned once, at registration time. `api_key` is never retrievable again --
    same handling as any bearer credential."""
    device_id: str
    api_key: str
    tourist_id: int


class DeviceOut(BaseModel):
    device_id: str
    tourist_id: int
    firmware_version: str
    battery_pct: float | None
    last_heartbeat: datetime | None
    active: bool
    is_online: bool

    class Config:
        from_attributes = True


class DeviceTelemetry(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    speed_kmh: float = Field(0.0, ge=0, le=1200)
    heart_rate_bpm: float | None = Field(None, ge=0, le=300)
    battery_pct: float | None = Field(None, ge=0, le=100)
    sos_pressed: bool = False
    fall_detected: bool = False
