"""Schemas for the Digital Tourist Safety ID (app/api/tourist_id.py)."""
from datetime import datetime

from pydantic import BaseModel, Field


class DigitalIdCardOut(BaseModel):
    digital_id: str
    full_name: str
    photo: str | None
    hotel: str | None
    trip_start: datetime
    trip_end: datetime
    id_status: str
    issued_at: datetime
    qr_png_base64: str | None


class ScanRequest(BaseModel):
    token: str | None = Field(None, max_length=200)
    digital_id: str | None = Field(None, max_length=60)
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)


class TouristIdScanOut(BaseModel):
    id: int
    tourist_id: int | None
    scanner_role: str
    method: str
    scanned_at: datetime
    verification_status: str
    accessed_fields: list[str]

    class Config:
        from_attributes = True


class PhotoUpdate(BaseModel):
    photo: str = Field(..., min_length=10, max_length=2_000_000)


class ReportIncidentFromScan(BaseModel):
    """Report/create an incident straight from a verified scan result --
    identifies the tourist by their public Tourist Safety ID, never the
    internal numeric id (the scan response never exposes that)."""
    digital_id: str = Field(..., max_length=60)
    description: str = Field(..., min_length=1, max_length=1000)
    severity: str = Field("medium", pattern="^(low|medium|high|critical)$")


class MyScanOut(BaseModel):
    id: int
    scanned_at: datetime
    verification_status: str
    digital_id: str | None
    full_name: str | None

