"""Festival & Local Event Intelligence: a calendar of festivals/fairs/local
events (app/models/festival.py), with "next occurrence" resolution for
recurring yearly events, and proximity/date filtering for "what's on near
me soon" and for services/crowd_forecast.py's festival-driven crowd bump.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.festival import Festival
from app.models.zone import Zone
from app.services import holidays
from app.services.geo import haversine_m, point_in_zone, zone_centroid


def _next_occurrence(festival: Festival, today: date) -> tuple[date, date]:
    """The next start/end date for this festival from `today`. For a
    recurring event whose stored dates already passed this year, roll the
    year forward (repeatedly, so a `start_date` from any past year still
    resolves to the correct *next* occurrence) until it's upcoming or in
    progress; a one-off event's dates are returned as-is."""
    start, end = festival.start_date, festival.end_date
    if not festival.recurring_yearly:
        return start, end

    while end < today:
        start = start.replace(year=start.year + 1)
        end = end.replace(year=end.year + 1)
    return start, end


def _serialize(f: Festival, today: date, distance_km: float | None = None) -> dict:
    start, end = _next_occurrence(f, today)
    return {
        "id": f.id, "name": f.name, "description": f.description, "category": f.category,
        "state": f.state, "lat": f.lat, "lng": f.lng,
        "next_start": start.isoformat(), "next_end": end.isoformat(),
        "crowd_impact": f.crowd_impact, "distance_km": distance_km, "source": "curated",
    }


def _public_holiday_rows(today: date, within_days: int) -> list[dict]:
    """Real national public holidays (services/holidays.py -- Nager.Date,
    no key) within `within_days`, in the same shape _serialize returns, so
    they merge into the calendar alongside the curated Festival rows rather
    than living as a separate, disconnected list. No location (a national
    holiday isn't tied to one point), so it never appears in a
    distance-filtered result -- see upcoming_near/upcoming_for_zone below.
    """
    rows = []
    for year in {today.year, today.year + 1}:
        for h in holidays.fetch_public_holidays(settings.HOLIDAYS_COUNTRY_CODE, year):
            h_date = date.fromisoformat(h["date"])
            if 0 <= (h_date - today).days <= within_days:
                rows.append({
                    "id": f"holiday:{h['date']}", "name": h["name"], "description": h.get("local_name", ""),
                    "category": "public_holiday", "state": None, "lat": None, "lng": None,
                    "next_start": h["date"], "next_end": h["date"],
                    "crowd_impact": "medium", "distance_km": None, "source": "public_holiday_api",
                })
    return rows


def list_festivals(
    db: Session, state: str | None = None, category: str | None = None,
    within_days: int | None = None, today: date | None = None,
) -> list[dict]:
    today = today or date.today()
    q = db.query(Festival)
    if state:
        q = q.filter(Festival.state == state)
    if category:
        q = q.filter(Festival.category == category)

    out = []
    for f in q.all():
        start, _end = _next_occurrence(f, today)
        if within_days is not None and (start - today).days > within_days:
            continue
        out.append(_serialize(f, today))
    if not category or category == "public_holiday":
        out.extend(_public_holiday_rows(today, within_days if within_days is not None else 365))
    out.sort(key=lambda r: r["next_start"])
    return out


def upcoming_near(
    db: Session, lat: float, lng: float, radius_km: float = 150, within_days: int = 60,
    today: date | None = None,
) -> list[dict]:
    """Festivals within `radius_km` of a point whose next occurrence starts
    within `within_days`. Events with no coordinates are skipped (no
    fabricated location) -- see /festivals for the un-filtered list."""
    today = today or date.today()
    out = []
    for f in db.query(Festival).filter(Festival.lat.isnot(None), Festival.lng.isnot(None)).all():
        start, _end = _next_occurrence(f, today)
        if (start - today).days > within_days:
            continue
        dist_km = haversine_m(lat, lng, f.lat, f.lng) / 1000
        if dist_km <= radius_km:
            out.append(_serialize(f, today, distance_km=round(dist_km, 1)))
    out.sort(key=lambda r: (r["next_start"], r["distance_km"]))
    return out


def on_date_near(db: Session, target_date: date, lat: float, lng: float, radius_km: float = 60) -> list[dict]:
    """Festivals (curated + real public holidays) whose window covers
    `target_date` and whose location (curated only -- a national holiday has
    none) is within `radius_km` of a point. Used by the Smart Trip Planner
    to flag "day 3 of your trip lands on Diwali near this stop" -- see
    services/trip_planner.py."""
    out = []
    for f in db.query(Festival).filter(Festival.lat.isnot(None), Festival.lng.isnot(None)).all():
        # Resolving "next occurrence as of target_date" (not today) gives the
        # occurrence that actually covers that future date, including the
        # boundary case where it started slightly before target_date.
        start, end = _next_occurrence(f, target_date)
        if not (start <= target_date <= end):
            continue
        dist_km = haversine_m(lat, lng, f.lat, f.lng) / 1000
        if dist_km <= radius_km:
            out.append(_serialize(f, today, distance_km=round(dist_km, 1)))
    for h in holidays.fetch_public_holidays(settings.HOLIDAYS_COUNTRY_CODE, target_date.year):
        if h["date"] == target_date.isoformat():
            out.append({
                "id": f"holiday:{h['date']}", "name": h["name"], "description": h.get("local_name", ""),
                "category": "public_holiday", "state": None, "lat": None, "lng": None,
                "next_start": h["date"], "next_end": h["date"],
                "crowd_impact": "medium", "distance_km": None, "source": "public_holiday_api",
            })
    return out


def upcoming_for_zone(db: Session, zone_id: int, within_days: int = 5, today: date | None = None) -> list[dict]:
    """Festivals whose location falls inside `zone_id`'s polygon (or, for a
    festival with no polygon-precise point, within the zone's centroid
    radius) and start within `within_days` -- used by crowd_forecast.py."""
    zone = db.get(Zone, zone_id)
    if zone is None:
        return []
    today = today or date.today()
    centroid = zone_centroid(zone)
    out = []
    for f in db.query(Festival).filter(Festival.lat.isnot(None), Festival.lng.isnot(None)).all():
        start, end = _next_occurrence(f, today)
        starting_soon = 0 <= (start - today).days <= within_days
        ongoing = start <= today <= end
        if not (starting_soon or ongoing):
            continue
        in_zone = point_in_zone(f.lat, f.lng, zone)
        near_centroid = centroid is not None and haversine_m(*centroid, f.lat, f.lng) <= 25_000
        if in_zone or near_centroid:
            out.append(_serialize(f, today))
    return out
