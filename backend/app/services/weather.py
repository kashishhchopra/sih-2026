"""Weather-risk adapter for the safety-score model.

`safety.py` needs one number: 0-100 weather risk. This has two
implementations behind that same interface:

  - real: OpenWeatherMap's free "current weather" endpoint, condition codes
    mapped to an explainable risk score.
  - mock: a deterministic function of lat/lng (the project's original
    behaviour), used whenever no API key is configured.

Falling back automatically (no key, API error, timeout) means the app never
depends on network access or a paid service to run -- required for an
offline demo -- while still being real when a key is provided.
"""
from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_cache: dict[tuple[float, float], tuple[float, float]] = {}  # (lat,lng) -> (risk, expires_at)
_CACHE_PRECISION = 1  # round to ~11km grid cells so nearby pings share a cache entry


def _cache_key(lat: float, lng: float) -> tuple[float, float]:
    return (round(lat, _CACHE_PRECISION), round(lng, _CACHE_PRECISION))


def mock_weather_risk(lat: float, lng: float) -> float:
    """Deterministic mock weather risk 0-100. No network, always available."""
    return round((abs(lat * 100 + lng * 100) % 60), 1)


def _condition_risk(weather_id: int) -> float:
    group = weather_id // 100
    if group == 2:  # thunderstorm
        return 80.0
    if group == 3:  # drizzle
        return 20.0
    if group == 5:  # rain
        return 60.0 if weather_id >= 502 else 30.0  # 502+ = heavy/violent/extreme
    if group == 6:  # snow
        return 50.0
    if group == 7:  # fog/dust/haze/tornado etc
        return 45.0
    if weather_id == 800:  # clear sky
        return 5.0
    return 10.0  # clouds (801-804)


def _fetch_openweathermap(lat: float, lng: float) -> float | None:
    try:
        resp = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lng, "appid": settings.OPENWEATHER_API_KEY,
                   "units": "metric"},
            timeout=settings.OPENWEATHER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("OpenWeatherMap request failed, falling back to mock: %s", e)
        return None

    weather_id = (data.get("weather") or [{}])[0].get("id", 800)
    risk = _condition_risk(weather_id)

    wind_speed = (data.get("wind") or {}).get("speed", 0.0)  # m/s
    if wind_speed > 15:
        risk += 20
    elif wind_speed > 10:
        risk += 10

    temp = (data.get("main") or {}).get("temp")
    if temp is not None and (temp > 42 or temp < 2):
        risk += 15

    return round(min(100.0, max(0.0, risk)), 1)


def get_weather_risk(lat: float, lng: float) -> float:
    """0-100 weather risk at a coordinate. Cached briefly to avoid a network
    call on every single GPS ping in the same neighbourhood."""
    if not settings.OPENWEATHER_API_KEY:
        return mock_weather_risk(lat, lng)

    key = _cache_key(lat, lng)
    cached = _cache.get(key)
    now = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    risk = _fetch_openweathermap(lat, lng)
    if risk is None:
        return mock_weather_risk(lat, lng)

    _cache[key] = (risk, now + settings.WEATHER_CACHE_TTL_SECONDS)
    return risk


_conditions_cache: dict[tuple[float, float], tuple[dict, float]] = {}  # (lat,lng) -> (conditions, expires_at)


def fetch_current_conditions(lat: float, lng: float) -> dict | None:
    """Real current-weather conditions at a coordinate -- the raw fields
    (condition code, description, temperature, wind speed), not the
    collapsed 0-100 risk number `get_weather_risk` returns. Used by
    services/disaster.py to derive genuine weather-hazard advisories
    (extreme heat, dense fog, thunderstorm, ...) straight from what
    OpenWeatherMap actually reported for that spot.

    None when no API key is configured or the request fails -- callers must
    treat that as "no data", never synthesize a hazard from nothing. Cached
    briefly (same TTL as the risk score) so scanning every zone on a
    disaster-feed tick doesn't multiply into one call per zone per minute.
    """
    if not settings.OPENWEATHER_API_KEY:
        return None

    key = _cache_key(lat, lng)
    cached = _conditions_cache.get(key)
    now = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    try:
        resp = httpx.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lng, "appid": settings.OPENWEATHER_API_KEY,
                   "units": "metric"},
            timeout=settings.OPENWEATHER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("OpenWeatherMap conditions request failed: %s", e)
        return None

    weather = (data.get("weather") or [{}])[0]
    conditions = {
        "weather_id": weather.get("id", 800),
        "description": weather.get("description", ""),
        "temp_c": (data.get("main") or {}).get("temp"),
        "wind_speed_ms": (data.get("wind") or {}).get("speed", 0.0),
        "observed_at": data.get("dt"),
    }
    _conditions_cache[key] = (conditions, now + settings.WEATHER_CACHE_TTL_SECONDS)
    return conditions


def clear_cache() -> None:
    _cache.clear()
    _conditions_cache.clear()
