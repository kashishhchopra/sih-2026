"""Smart Trip Planner: turns a tourist's confirmed itinerary (the same
`Tourist.itinerary` waypoint list the map/geofence code already reads) into a
day-by-day plan, checked against real signals for each day rather than a
static list:

  - weather (services/weather.py) -- flags a bad day and swaps in a real
    indoor alternative (services/discovery.py's live Overpass lookup) rather
    than just saying "reconsider this day".
  - festivals & public holidays (services/festival.py) -- a festival landing
    on a planned day near a planned stop is surfaced on that day, not buried
    in a separate calendar.
  - permits (services/permit.py) -- a stop that falls inside a zone whose
    risk level suggests a permit is flagged on that day.

Never mutates the tourist's real itinerary -- this is a read-only planning
view over it, recomputed fresh from live data on every call.
"""
from __future__ import annotations

import json
import math
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.tourist import Tourist
from app.models.zone import Zone
from app.services import discovery, permit as permit_service
from app.services.festival import on_date_near
from app.services.geo import zones_containing_point
from app.services.weather import get_weather_risk

# Bounded so a very long trip can't blow up the response / compute budget.
MAX_PLANNED_DAYS = 14
# A day whose worst-stop weather risk crosses this is flagged for re-planning.
_REPLAN_RISK_THRESHOLD = 55.0


def _weather_band(risk: float) -> str:
    if risk >= _REPLAN_RISK_THRESHOLD:
        return "poor"
    if risk >= 30:
        return "fair"
    return "good"


def _advisory(band: str, indoor_alt: dict | None) -> str:
    if band == "poor":
        if indoor_alt:
            return (
                f"Weather risk is high for this day -- consider {indoor_alt['name']} "
                f"({indoor_alt['distance_km']} km away) as an indoor alternative instead."
            )
        return "Weather risk is high for this day -- consider an indoor/low-exposure alternative or reordering this stop to another day."
    if band == "fair":
        return "Weather is mixed -- keep a light rain layer and check conditions before heading out."
    return "Conditions look favourable for this day's plan."


def generate_trip_plan(db: Session, tourist: Tourist, days: int | None = None) -> dict:
    """Distribute the tourist's confirmed itinerary stops across `days` (or
    the tourist's actual trip length, capped at MAX_PLANNED_DAYS), and attach
    a per-day weather/festival/permit check, all computed live -- nothing in
    the returned plan is hardcoded."""
    waypoints = json.loads(tourist.itinerary or "[]")
    now = utc_now()
    notes: list[str] = []

    if days is None:
        span = (tourist.trip_end.date() - tourist.trip_start.date()).days + 1
        days = max(1, span)
    days = max(1, min(days, MAX_PLANNED_DAYS))

    if not waypoints:
        notes.append("No confirmed itinerary yet -- upload or add destinations to generate a real plan.")
        return {
            "tourist_id": tourist.id, "generated_at": now.isoformat(),
            "days": [], "replanning_suggested": False, "notes": notes,
        }

    zones = db.query(Zone).all()
    per_day = max(1, math.ceil(len(waypoints) / days))
    replanning_suggested = False
    plan_days = []

    for day_idx in range(days):
        chunk = waypoints[day_idx * per_day:(day_idx + 1) * per_day]
        if not chunk and day_idx > 0:
            break
        stops = [
            {"name": w.get("name", "Stop"), "lat": w.get("lat"), "lng": w.get("lng")}
            for w in chunk
        ]
        located_stops = [s for s in stops if s["lat"] is not None and s["lng"] is not None]
        plan_date = tourist.trip_start.date() + timedelta(days=day_idx)

        # Worst-case weather risk across the day's stops -- a day is only as
        # safe as its riskiest planned stop.
        risks = [get_weather_risk(s["lat"], s["lng"]) for s in located_stops]
        risk = max(risks) if risks else 0.0
        band = _weather_band(risk)

        indoor_alt = None
        if band == "poor" and located_stops:
            worst_stop = max(located_stops, key=lambda s: get_weather_risk(s["lat"], s["lng"]))
            alternatives = discovery.find_indoor_alternatives(worst_stop["lat"], worst_stop["lng"])
            indoor_alt = alternatives[0] if alternatives else None
            replanning_suggested = True

        festivals_today: list[dict] = []
        permits_needed: set[str] = set()
        for s in located_stops:
            festivals_today.extend(on_date_near(db, plan_date, s["lat"], s["lng"]))
            for zone in zones_containing_point(s["lat"], s["lng"], zones):
                permits_needed.update(permit_service.required_for_zone(zone))
        # de-duplicate festivals that matched more than one stop the same day
        seen = set()
        festivals_today = [f for f in festivals_today if not (f["id"] in seen or seen.add(f["id"]))]

        plan_days.append({
            "day": day_idx + 1,
            "date": plan_date.isoformat(),
            "stops": stops,
            "weather_risk": risk,
            "weather_band": band,
            "advisory": _advisory(band, indoor_alt),
            "indoor_alternative": indoor_alt,
            "festivals": festivals_today,
            "permits_suggested": sorted(permits_needed),
        })

    if len(waypoints) > per_day * days:
        notes.append(
            f"{len(waypoints) - per_day * days} destination(s) didn't fit in {days} day(s) "
            "and were left off the plan -- widen the trip window or add more days."
        )
    if replanning_suggested:
        notes.append("One or more days show poor weather at a planned stop -- re-planning suggested.")
    if any(d["festivals"] for d in plan_days):
        notes.append("A festival or public holiday falls on one or more of your planned days -- expect extra crowds.")
    if any(d["permits_suggested"] for d in plan_days):
        notes.append("One or more stops may require a permit -- see the Permits & E-Pass section.")

    return {
        "tourist_id": tourist.id, "generated_at": now.isoformat(),
        "days": plan_days, "replanning_suggested": replanning_suggested, "notes": notes,
    }
