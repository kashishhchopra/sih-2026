"""Schemas for the CCTV network (app/api/cctv.py, services/cctv.py)."""
from datetime import datetime

from pydantic import BaseModel


class CctvCameraOut(BaseModel):
    """One camera as the Police Network Dashboard sees it.

    `status` is the operator's enable/disable flag; `connection` is the
    probed live state -- they are separate on purpose, so nothing can read
    LIVE merely because a row exists. `stream_url` has already had any
    credentials stripped server-side (services/cctv.py:_strip_credentials).
    """
    id: int
    label: str
    zone_id: int | None = None
    lat: float
    lng: float
    status: str
    installed_at: datetime | None = None
    stream_url: str | None = None
    stream_type: str
    feed_source: str
    source_url: str | None = None
    attribution: str | None = None
    assigned_station_id: int | None = None
    connection: str
    last_checked_at: datetime | None = None


class CctvNetworkSummary(BaseModel):
    total: int
    live: int
    offline: int
    no_stream: int
    unavailable: int = 0
    provider: str | None = None
    provider_configured: bool
    refresh_interval_seconds: int


class CctvNetworkOut(BaseModel):
    cameras: list[CctvCameraOut]
    summary: CctvNetworkSummary


class CctvStatusOut(BaseModel):
    id: int
    connection: str
    last_checked_at: datetime | None = None


class CctvRefreshOut(BaseModel):
    configured: bool
    imported: int
    updated: int
    detail: str
