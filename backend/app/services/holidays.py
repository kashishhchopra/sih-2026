"""Real public holidays via the Calendarific API (https://calendarific.com)
-- same "real when a key is configured, honest empty result when it isn't"
shape as services/weather.py and services/translation.py.

Nager.Date (https://date.nager.at) was tried first since it needs no key at
all, but it does not cover India (`/AvailableCountries` doesn't list "IN"),
so it can't back this feature for this deployment's actual tourists.
Calendarific does cover India and 200+ other countries on its free tier
(a `CALENDARIFIC_API_KEY` env var -- see backend/.env.example). With no key
configured, holiday-aware features simply have no holiday signal for that
request -- never a fabricated one.
"""
from __future__ import annotations

import logging
import time
from datetime import date

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://calendarific.com/api/v2/holidays"

_cache: dict[tuple[str, int], tuple[list[dict], float]] = {}  # (country, year) -> (holidays, expires_at)


def _cache_key(country_code: str, year: int) -> tuple[str, int]:
    return (country_code.upper(), year)


def fetch_public_holidays(country_code: str = "IN", year: int | None = None) -> list[dict]:
    """[{date: "YYYY-MM-DD", name, local_name}, ...] for `country_code` in
    `year` (default: this year). Cached for the process lifetime per
    (country, year) -- a year's public holidays don't change once published.
    Returns [] (never raises, never invents a holiday) if no API key is
    configured or the request fails."""
    year = year or date.today().year
    if not settings.CALENDARIFIC_API_KEY:
        return []

    key = _cache_key(country_code, year)
    cached = _cache.get(key)
    now = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    try:
        resp = httpx.get(
            _BASE_URL,
            params={
                "api_key": settings.CALENDARIFIC_API_KEY, "country": country_code.upper(),
                "year": year, "type": "national",
            },
            timeout=settings.HOLIDAYS_API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Calendarific request failed for %s/%s: %s", country_code, year, e)
        return cached[0] if cached else []  # serve stale cache over nothing if we have it

    raw = (data.get("response") or {}).get("holidays") or []
    holidays = [
        {"date": h["date"]["iso"][:10], "name": h.get("name", ""), "local_name": h.get("name", "")}
        for h in raw if (h.get("date") or {}).get("iso")
    ]
    _cache[key] = (holidays, now + settings.HOLIDAYS_CACHE_TTL_SECONDS)
    return holidays


def holiday_on(day: date, country_code: str = "IN") -> dict | None:
    """The public holiday falling on `day`, or None."""
    for h in fetch_public_holidays(country_code, day.year):
        if h["date"] == day.isoformat():
            return h
    return None


def is_holiday_window(day: date, window_days: int = 2, country_code: str = "IN") -> dict | None:
    """A real public holiday within `window_days` of `day` (a holiday itself
    plus the travel-heavy days around it), or None. Returns the nearest such
    holiday's info so the caller can say *which* holiday, not just yes/no."""
    from datetime import timedelta

    best: dict | None = None
    best_delta = None
    for offset in range(-window_days, window_days + 1):
        candidate = day + timedelta(days=offset)
        h = holiday_on(candidate, country_code)
        if h and (best_delta is None or abs(offset) < best_delta):
            best, best_delta = h, abs(offset)
    return best


def clear_cache() -> None:
    _cache.clear()
