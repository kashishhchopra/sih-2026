"""Canonical time helpers.

The codebase stores naive-UTC datetimes in every DateTime column (SQLite has no
tz-aware type, and the Postgres columns are declared without timezone). Mixing
`datetime.utcnow()`, `datetime.now(timezone.utc).replace(tzinfo=None)` and naive
local `datetime.now()` had crept in across services; everything now goes through
here so "what time is it" has exactly one answer.
"""
from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Current UTC time as a *naive* datetime, matching the DB column convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def utc_now_aware() -> datetime:
    """Current UTC time as a tz-aware datetime (for JWT claims and ISO output)."""
    return datetime.now(UTC)


def local_hour_for(lat: float | None, lng: float | None) -> int:
    """Approximate local hour-of-day at a coordinate, 0-23.

    The safety model applies a night-time penalty, which previously used the
    *server's* local hour — so a tourist in Guwahati got a night penalty based on
    where the server happened to be hosted. Longitude gives a good-enough solar
    offset (15 deg per hour) without a timezone database dependency.
    """
    if lng is None:
        return utc_now().hour
    offset_hours = round(lng / 15.0)
    return (utc_now().hour + offset_hours) % 24
