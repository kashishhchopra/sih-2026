"""Schemas for itinerary document upload/extraction (app/api/itinerary.py)."""
from datetime import date, datetime

from pydantic import BaseModel, Field


class ExtractedDestination(BaseModel):
    name: str
    lat: float | None = None
    lng: float | None = None
    location_demo: bool | None = None


class ExtractedHotel(BaseModel):
    name: str
    check_in: bool = False
    check_out: bool = False


class ExtractedTransport(BaseModel):
    detail: str


class ExtractedItinerary(BaseModel):
    """The structured, tourist-editable result of parsing an uploaded
    document -- see services/itinerary_extract.py:parse_itinerary_text."""
    trip_start: date | None = None
    trip_end: date | None = None
    destinations: list[ExtractedDestination] = Field(default_factory=list)
    hotels: list[ExtractedHotel] = Field(default_factory=list)
    transport: list[ExtractedTransport] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)


class ItineraryDocumentOut(BaseModel):
    id: int
    tourist_id: int
    filename: str
    content_type: str
    uploaded_at: datetime
    status: str
    error: str
    extracted: ExtractedItinerary
    confirmed: bool
    confirmed_at: datetime | None
