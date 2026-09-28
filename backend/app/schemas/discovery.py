"""Schemas for the Discovery feature (app/api/discovery.py)."""
from pydantic import BaseModel, Field


class DiscoveryPlace(BaseModel):
    id: int | str
    name: str
    category: str
    lat: float
    lng: float
    distance_km: float
    tip: str = ""
    source: str = "manual"


class DiscoveryResponse(BaseModel):
    lat: float
    lng: float
    radius_km: float
    places: list[DiscoveryPlace] = Field(default_factory=list)


class OfflineBundle(BaseModel):
    generated_at: str
    lat: float
    lng: float
    radius_km: float
    places: list[DiscoveryPlace] = Field(default_factory=list)
