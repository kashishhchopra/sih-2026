"""Disaster & Weather Alert Feeds: area-level hazard advisories (flood,
landslide, earthquake, storm), distinct from the per-tourist weather-risk
factor in services/weather.py.

Two candidate sources, chosen by DISASTER_FEED_PROVIDER:
  - "" (default): the deterministic simulator, seeded per zone+day so
    results are stable within a day (not random noise on every tick) while
    still varying zone to zone. No external dependency at all.
  - "cap": a real CAP 1.2 feed at DISASTER_FEED_URL (see services/cap.py and
    fetch_real_feed_candidates), matched onto local zones by polygon
    intersection. Falls through to the simulator if the feed is
    unreachable/unparseable on a given tick -- see tick_disaster_feed.

Everything else -- persistence, zone matching, tourist notification -- is
identical regardless of which source produced the candidates.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utc_now
from app.models.disaster import DisasterAdvisory
from app.models.tourist import Tourist
from app.models.zone import Zone
from app.services import cap, feeds, weather
from app.services.geo import zone_centroid, zones_containing_point, zones_intersecting_polygon

logger = get_logger(__name__)

_HAZARDS_BY_RISK = {
    "restricted": ["flood", "landslide", "earthquake"],
    "high": ["landslide", "storm", "flood"],
    "medium": ["storm"],
    "low": [],
}
_SEVERITY_FOR_ZONE_RISK = {"restricted": "critical", "high": "high", "medium": "medium", "low": "low"}

_MESSAGES = {
    "flood": "Flash flood advisory in effect. Avoid riverbanks and low-lying areas.",
    "landslide": "Landslide risk elevated after recent rainfall. Avoid steep/unstable slopes.",
    "earthquake": "Regional seismic activity advisory. Know your nearest open ground.",
    "storm": "Severe storm warning. Seek sturdy shelter and avoid open areas.",
}

# Static safety guidance per hazard type -- what to DO, independent of
# whether any given occurrence is real. Every hazard_type this module can
# produce (simulator, CAP feed, or the real-weather-condition detector
# below) gets one; unmapped types (a CAP feed can carry an event this app
# has no keyword for) fall back to a generic instruction rather than blank.
_INSTRUCTIONS = {
    "flood": "Move to higher ground immediately. Avoid walking or driving through flood water.",
    "landslide": "Move away from steep slopes and unstable ground. Report cracks or unusual sounds from hillsides.",
    "earthquake": "Drop, cover, and hold on. Stay away from windows and heavy furniture until shaking stops.",
    "storm": "Seek sturdy shelter indoors. Avoid open areas, tall trees, and metal structures.",
    "heavy_rain": "Avoid low-lying roads and underpasses. Allow extra time and distance if travelling.",
    "thunderstorm": "Stay indoors. Avoid open fields, water, and isolated tall structures until it passes.",
    "extreme_heat": "Stay hydrated, avoid direct sun 11am-4pm, and watch for signs of heat exhaustion.",
    "extreme_cold": "Dress in layers, limit time outdoors, and watch for signs of hypothermia/frostbite.",
    "dense_fog": "Reduce travel speed, use fog lights, and avoid unnecessary road/water travel.",
}
_DEFAULT_INSTRUCTION = "Follow guidance from local authorities and monitor official channels for updates."


def _title_for(hazard_type: str) -> str:
    return f"{hazard_type.replace('_', ' ').title()} Advisory"


def _instructions_for(hazard_type: str) -> str:
    return _INSTRUCTIONS.get(hazard_type, _DEFAULT_INSTRUCTION)


# ---- real weather-condition hazard detector -------------------------------
# A second, independent real-data source alongside the CAP feed above: where
# fetch_real_feed_candidates matches an official *advisory document* onto a
# zone, this derives a hazard candidate straight from OpenWeatherMap's
# *actual current reading* at each zone's centroid (services/weather.py).
# Thresholds are real meteorological numbers, not simulated -- a zone only
# ever gets a candidate here when the live API response crosses one. No
# API key configured -> weather.fetch_current_conditions returns None for
# every zone -> this contributes nothing, same as before this existed.
_FOG_CODES = {741, 701}  # OpenWeatherMap condition ids: fog, mist


def _weather_hazard_for_conditions(c: dict) -> tuple[str, str] | None:
    """(hazard_type, severity) for one real OpenWeatherMap reading, or None
    if nothing in it crosses a hazard threshold. Checked most-severe-signal
    first since a reading can technically match more than one bucket."""
    weather_id = c.get("weather_id", 800)
    temp = c.get("temp_c")
    wind = c.get("wind_speed_ms") or 0.0

    if weather_id // 100 == 2:  # thunderstorm group
        return ("thunderstorm", "high")
    if temp is not None and temp >= 45:
        return ("extreme_heat", "critical")
    if temp is not None and temp >= 42:
        return ("extreme_heat", "high")
    if temp is not None and temp <= -5:
        return ("extreme_cold", "critical")
    if temp is not None and temp <= 2:
        return ("extreme_cold", "medium")
    if weather_id // 100 == 5 and weather_id >= 502:  # heavy/violent/extreme rain (5xx group only)
        return ("heavy_rain", "high")
    if wind > 20:
        return ("storm", "high")
    if weather_id in _FOG_CODES:
        return ("dense_fog", "medium")
    return None


def weather_condition_advisories(zones: list[Zone]) -> list[dict]:
    """Real weather-condition candidates, one per zone whose centroid's
    *current* OpenWeatherMap reading crosses a hazard threshold. Returns []
    outright when OPENWEATHER_API_KEY isn't configured (weather.py already
    guards that), so this is a strict no-op addition when unused."""
    if not settings.OPENWEATHER_API_KEY:
        return []
    out = []
    for zone in zones:
        centroid = zone_centroid(zone)
        if centroid is None:
            continue
        conditions = weather.fetch_current_conditions(*centroid)
        if conditions is None:
            continue
        hazard = _weather_hazard_for_conditions(conditions)
        if hazard is None:
            continue
        hazard_type, severity = hazard
        desc = conditions.get("description") or hazard_type.replace("_", " ")
        out.append({
            "zone_id": zone.id,
            "hazard_type": hazard_type,
            "severity": severity,
            "message": f"Current conditions: {desc} ({conditions.get('temp_c')}°C).",
            "source": "openweathermap",
        })
    return out


def _daily_seed(zone_id: int, hazard: str) -> int:
    """Deterministic per (zone, hazard, day) seed -- stable through a day's
    demo, changes tomorrow, never random noise on every tick."""
    key = f"{zone_id}:{hazard}:{utc_now().date().isoformat()}"
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


def _fetch_cap_xml() -> str | None:
    import httpx

    resp = httpx.get(settings.DISASTER_FEED_URL, timeout=settings.FEED_TIMEOUT_SECONDS,
                     headers={"User-Agent": "smart-tourist-safety/1.0"})
    resp.raise_for_status()
    return resp.text


def fetch_real_feed_candidates(zones: list[Zone]) -> list[dict] | None:
    """Real CAP-feed candidates matched onto local zones by geometry, or
    None if no real feed is configured/reachable (falls through to the
    simulator -- see tick_disaster_feed). Goes through the same live/cache/
    snapshot ladder as every other external feed (services/feeds.py)."""
    if not settings.DISASTER_FEED_URL:
        return None

    xml_text, source = feeds.fetch_with_snapshot("disaster_cap", _fetch_cap_xml)
    if xml_text is None:
        return None

    try:
        alerts = cap.parse_cap_feed(xml_text.encode("utf-8"))
    except Exception as e:  # noqa: BLE001 -- a malformed feed must not crash the tick
        logger.warning("disaster_cap_parse_failed", error=str(e))
        return None

    out = []
    for alert in alerts:
        polygon = alert.get("polygon")
        matched_zones = zones_intersecting_polygon(polygon, zones) if polygon else []
        for zone in matched_zones:
            out.append({
                "zone_id": zone.id,
                "hazard_type": alert["hazard_type"],
                "severity": alert["severity"],
                "message": alert["message"],
                "source": f"cap:{source}",
                "external_id": alert.get("external_id"),
                "area_desc": alert.get("area_desc"),
            })
    return out


def simulate_advisories(zones: list[Zone]) -> list[dict]:
    """One candidate advisory per (zone, plausible hazard for that zone's
    risk level) that "fires" today, deterministically."""
    out = []
    for zone in zones:
        for hazard in _HAZARDS_BY_RISK.get(zone.risk_level, []):
            # ~1-in-4 chance per hazard per zone per day -- infrequent enough
            # that a demo doesn't drown in advisories, frequent enough that
            # one reliably fires within a session.
            if _daily_seed(zone.id, hazard) % 4 != 0:
                continue
            out.append({
                "zone_id": zone.id,
                "hazard_type": hazard,
                "severity": _SEVERITY_FOR_ZONE_RISK.get(zone.risk_level, "medium"),
                "message": _MESSAGES[hazard],
                "source": "simulated",
            })
    return out


def tick_disaster_feed(db: Session) -> dict[str, list[int]]:
    """Refresh advisories: expire ones no longer indicated, create new ones,
    and alert every tourist currently inside a newly-active advisory's zone.
    Runs on the same scheduler as check-ins/escalation (see app/main.py).
    """
    from app.services.monitoring import _create_alert  # local import: avoid a top-level cycle

    zones = db.query(Zone).all()

    candidates = None
    if settings.DISASTER_FEED_PROVIDER == "cap":
        candidates = fetch_real_feed_candidates(zones)
    if candidates is None:
        candidates = simulate_advisories(zones)
    # Real weather-condition candidates (see weather_condition_advisories'
    # docstring) are always merged in on top of whichever source above ran
    # -- independent real data, not an either/or with CAP/simulator. A no-op
    # when OPENWEATHER_API_KEY isn't configured.
    candidates = candidates + weather_condition_advisories(zones)
    candidate_keys = {(c["zone_id"], c["hazard_type"]) for c in candidates}

    active = db.query(DisasterAdvisory).filter(DisasterAdvisory.active.is_(True)).all()
    active_keys = {(a.zone_id, a.hazard_type) for a in active}

    expired: list[int] = []
    for a in active:
        if (a.zone_id, a.hazard_type) not in candidate_keys:
            a.active = False
            expired.append(a.id)

    created: list[int] = []
    tourists = db.query(Tourist).filter(
        Tourist.last_lat.isnot(None), Tourist.last_lng.isnot(None),
    ).all()
    for c in candidates:
        if (c["zone_id"], c["hazard_type"]) in active_keys:
            continue  # already active, nothing to do
        zone_for_advisory = next(z for z in zones if z.id == c["zone_id"])
        centroid = zone_centroid(zone_for_advisory)
        advisory = DisasterAdvisory(
            zone_id=c["zone_id"], hazard_type=c["hazard_type"], severity=c["severity"],
            message=c["message"], source=c["source"],
            external_id=c.get("external_id"), area_desc=c.get("area_desc"),
            title=_title_for(c["hazard_type"]), instructions=_instructions_for(c["hazard_type"]),
            latitude=centroid[0] if centroid else None, longitude=centroid[1] if centroid else None,
            expires_at=utc_now() + timedelta(hours=6),
        )
        db.add(advisory)
        db.flush()
        created.append(advisory.id)

        zone = zone_for_advisory
        affected = [t for t in tourists if zones_containing_point(t.last_lat, t.last_lng, [zone])]
        for t in affected:
            _create_alert(
                db, t.id, "disaster", c["severity"],
                f"⚠ {c['hazard_type'].title()} advisory for {zone.name}: {c['message']}",
                t.last_lat, t.last_lng, zone_id=zone.id,
                disaster_advisory_id=advisory.id,
            )
        logger.warning("disaster_advisory_issued", zone_id=zone.id, hazard=c["hazard_type"],
                       tourists_notified=len(affected))

    if created or expired:
        db.commit()
    return {"created": created, "expired": expired}


def active_advisories_for_tourist(db: Session, tourist: Tourist) -> list[DisasterAdvisory]:
    if tourist.last_lat is None:
        return []
    zones = db.query(Zone).all()
    inside = zones_containing_point(tourist.last_lat, tourist.last_lng, zones)
    zone_ids = [z.id for z in inside]
    if not zone_ids:
        return []
    return (
        db.query(DisasterAdvisory)
        .filter(DisasterAdvisory.zone_id.in_(zone_ids), DisasterAdvisory.active.is_(True))
        .all()
    )


def notify_tourist_of_active_disasters(db: Session, tourist: Tourist, zones_now_inside: list[Zone]) -> list[int]:
    """Called from the GPS-ping path (services/monitoring.py::process_ping),
    right alongside the existing geofence check, for exactly the zones the
    tourist is inside *right now*. tick_disaster_feed only ever notifies at
    the moment an advisory is first issued -- a tourist who enters an
    already-active hazard zone later (the common case: the advisory existed
    before they arrived) would otherwise never be told. This covers that.

    Dedup is per (disaster_advisory_id, tourist_id) via Alert.disaster_advisory_id
    -- a tourist already alerted for a given advisory is never re-alerted on
    every subsequent ping while they remain inside the zone. Returns the ids
    of any advisories newly notified this call.
    """
    from app.models.alert import Alert
    from app.services.monitoring import _create_alert  # local import: avoid a top-level cycle

    if not zones_now_inside:
        return []
    zone_ids = [z.id for z in zones_now_inside]
    active = (
        db.query(DisasterAdvisory)
        .filter(DisasterAdvisory.zone_id.in_(zone_ids), DisasterAdvisory.active.is_(True))
        .all()
    )
    if not active:
        return []

    already_notified = {
        row[0] for row in db.query(Alert.disaster_advisory_id).filter(
            Alert.tourist_id == tourist.id,
            Alert.disaster_advisory_id.in_([a.id for a in active]),
        ).all()
    }

    notified: list[int] = []
    zones_by_id = {z.id: z for z in zones_now_inside}
    for advisory in active:
        if advisory.id in already_notified:
            continue
        zone = zones_by_id[advisory.zone_id]
        _create_alert(
            db, tourist.id, "disaster", advisory.severity,
            f"⚠ {advisory.hazard_type.title()} advisory for {zone.name}: {advisory.message}",
            tourist.last_lat, tourist.last_lng, zone_id=zone.id,
            disaster_advisory_id=advisory.id,
        )
        notified.append(advisory.id)
    return notified


def affected_tourist_count(db: Session, advisory: DisasterAdvisory) -> int:
    """How many tourists are currently inside this advisory's zone -- for
    the Police Network Dashboard's "Affected Tourists" figure."""
    zone = db.get(Zone, advisory.zone_id)
    if zone is None:
        return 0
    tourists = db.query(Tourist).filter(
        Tourist.last_lat.isnot(None), Tourist.last_lng.isnot(None),
    ).all()
    return sum(1 for t in tourists if zones_containing_point(t.last_lat, t.last_lng, [zone]))
