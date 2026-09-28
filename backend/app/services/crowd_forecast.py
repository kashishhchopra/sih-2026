"""Crowd & Queue Forecast: extends the existing Crowd Density Detection
(services/crowd_density.py -- live tourist concentration per zone) with the
forward-looking factors from the notebook sketch: peak/off-peak season,
holiday periods, weather, and active local festivals/events (see
services/festival.py), plus a per-POI queue-wait estimate.

The season table below is the one genuinely unavoidable heuristic here (no
API publishes "is this India's tourist season" as a boolean) -- everything
else that can come from a real source now does: holiday periods come from
the free Nager.Date public-holiday API (services/holidays.py), not a
hand-maintained date table, so the "is there a holiday driving travel right
now, and which one" answer is real and labeled with the actual holiday name.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.place import PointOfInterest
from app.services import crowd_density, holidays
from app.services.festival import upcoming_for_zone
from app.services.geo import zone_centroid
from app.services.weather import get_weather_risk

# India's broad tourist-season calendar: Oct-Mar is the classic peak window
# (cooler weather across most of the country, major festival cluster);
# Jul-Sep (monsoon) and Apr-Jun (summer heat) are off-peak in most regions.
# This is the one signal with no API to source it from -- everything else in
# this module (holidays, festivals, weather, live tourist density) is real,
# fetched or database-backed data.
_PEAK_MONTHS = {10, 11, 12, 1, 2, 3}

_QUEUE_MINUTES = {"low": 5, "medium": 18, "high": 40}


def current_season(today: date | None = None) -> str:
    today = today or date.today()
    return "peak" if today.month in _PEAK_MONTHS else "off-peak"


def holiday_period_info(today: date | None = None) -> dict | None:
    """The real public holiday (name + date) within a few days of `today`,
    from services/holidays.py -- or None if there isn't one / the API is
    unreachable. Never a fabricated holiday."""
    today = today or date.today()
    return holidays.is_holiday_window(today, window_days=2, country_code=settings.HOLIDAYS_COUNTRY_CODE)


def _bump_band(band: str, steps: int) -> str:
    order = ["low", "medium", "high"]
    idx = min(len(order) - 1, order.index(band) + max(0, steps))
    return order[idx]


def forecast_zone_crowds(db: Session, today: date | None = None) -> list[dict]:
    """Per-zone crowd forecast: today's live density (crowd_density.py)
    adjusted forward by season, holiday period, active nearby festivals, and
    weather -- each a `reasons[]` entry so the number is always explainable,
    never a black box."""
    today = today or date.today()
    season = current_season(today)
    holiday = holiday_period_info(today)
    base_report = crowd_density.zone_density_report(db)

    out = []
    for row in base_report:
        reasons: list[str] = []
        bump = 0

        if season == "peak":
            reasons.append("Peak tourist season (Oct-Mar)")
            bump += 1
        if holiday:
            reasons.append(f"Near {holiday['name']} ({holiday['date']}) -- a public holiday travel window")
            bump += 1

        festivals = upcoming_for_zone(db, row["zone_id"], within_days=5)
        if festivals:
            reasons.append(f"{len(festivals)} festival/event nearby in the next 5 days")
            bump += 1

        # Fair weather draws more foot traffic to outdoor attractions than
        # poor weather does -- treated as a mild upward, not downward, bump
        # since low weather-risk conditions are what push more people outside.
        zone = next((z for z in db.query(crowd_density.Zone).all() if z.id == row["zone_id"]), None)
        centroid = zone_centroid(zone) if zone else None
        if centroid:
            risk = get_weather_risk(*centroid)
            if risk < 20:
                reasons.append("Favourable weather expected to draw more visitors")
                bump += 1

        forecast_density = _bump_band(row["density"], bump) if bump else row["density"]
        out.append({
            "zone_id": row["zone_id"],
            "zone": row["zone"],
            "tourist_count": row["tourist_count"],
            "current_density": row["density"],
            "season": season,
            "is_holiday_period": holiday is not None,
            "holiday_name": holiday["name"] if holiday else None,
            "active_festivals": [f["name"] for f in festivals],
            "forecast_density": forecast_density,
            "reasons": reasons or ["No elevated crowd factors detected"],
        })
    return out


def estimate_queue_wait(db: Session, poi_id: int) -> dict | None:
    """Rough queue-wait estimate at a point of interest, derived from the
    surrounding zone's forecast crowd band (not a live queue sensor -- none
    exists -- so this is explicitly an estimate, minutes are a fixed table
    per band, matching the honesty convention used throughout this file)."""
    poi = db.get(PointOfInterest, poi_id)
    if poi is None:
        return None

    band = "low"
    for zone in db.query(crowd_density.Zone).all():
        from app.services.geo import point_in_zone
        if point_in_zone(poi.lat, poi.lng, zone):
            report = next((r for r in forecast_zone_crowds(db) if r["zone_id"] == zone.id), None)
            if report:
                band = report["forecast_density"]
            break

    return {
        "poi_id": poi.id, "name": poi.name, "category": poi.category,
        "estimated_wait_minutes": _QUEUE_MINUTES[band], "band": band,
    }
