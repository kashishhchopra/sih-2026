"""Discovery: hidden/off-the-beaten-path spots, regional food, and homestays
near the tourist -- the "go beyond the obvious sights" sibling of
services/nearby.py's safety-infrastructure lookup (hospital/police/pharmacy/
transport).

Real data, live: unlike services/poi.py (a committed *snapshot* of police/
hospital OSM data, refreshed manually via app/scripts/fetch_pois.py because
Overpass rate-limits a bulk one-off pull), this module queries the public
OpenStreetMap Overpass API live, per request -- a short timeout and an
in-process cache (same shape as services/weather.py's) keep that safe to do
synchronously, and any failure/timeout falls back to whatever's already in
the `points_of_interest` table (seeded fixtures or a previous successful
live fetch -- see seed.py) rather than blocking the page or inventing places.

Also exposes a compact "offline bundle": the same data trimmed to fields a
low-connectivity device can cache client-side (see frontend/src/lib/
discoveryService.js, which stores it in localStorage) so Discovery still
works with no signal.
"""
from __future__ import annotations

import logging
import time

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models.place import PointOfInterest
from app.services.geo import haversine_m

logger = logging.getLogger(__name__)

DISCOVERY_CATEGORIES = ("hidden_gem", "regional_food", "homestay")

# OSM tag -> this app's Discovery category. Deliberately narrower than
# "every restaurant"/"every viewpoint" on OSM -- tags chosen to lean toward
# the "off the obvious path" framing this feature promises (viewpoints,
# artworks and local museums over mainstream "tourism=attraction", guest
# houses/homestays over hotels, named eateries with a cuisine tag over any
# fast-food node).
_OVERPASS_QUERY = """
[out:json][timeout:{timeout}];
(
  node["tourism"="viewpoint"](around:{radius_m},{lat},{lng});
  node["tourism"="artwork"](around:{radius_m},{lat},{lng});
  node["historic"]["name"](around:{radius_m},{lat},{lng});
  node["amenity"="restaurant"]["cuisine"]["name"](around:{radius_m},{lat},{lng});
  node["amenity"="cafe"]["cuisine"]["name"](around:{radius_m},{lat},{lng});
  node["tourism"="guest_house"]["name"](around:{radius_m},{lat},{lng});
  node["tourism"="homestay"]["name"](around:{radius_m},{lat},{lng});
);
out center tags;
"""

_TAG_TO_CATEGORY = {
    "viewpoint": "hidden_gem", "artwork": "hidden_gem", "historic": "hidden_gem",
    "restaurant": "regional_food", "cafe": "regional_food",
    "guest_house": "homestay", "homestay": "homestay",
}

_cache: dict[tuple[float, float, float], tuple[list[dict], float]] = {}  # (lat,lng,radius) -> (places, expires_at)
_CACHE_PRECISION = 2  # ~1.1km grid cells


def _cache_key(lat: float, lng: float, radius_km: float) -> tuple[float, float, float]:
    return (round(lat, _CACHE_PRECISION), round(lng, _CACHE_PRECISION), radius_km)


def _element_category(tags: dict) -> str | None:
    for key in ("tourism", "historic", "amenity"):
        val = tags.get(key)
        if key == "historic" and val:  # historic=* -- any value counts as historic
            return "hidden_gem"
        if val in _TAG_TO_CATEGORY:
            return _TAG_TO_CATEGORY[val]
    return None


def _tip_from_tags(tags: dict, category: str) -> str:
    if category == "regional_food" and tags.get("cuisine"):
        return f"Cuisine: {tags['cuisine'].replace(';', ', ').replace('_', ' ')}"
    if tags.get("description"):
        return tags["description"]
    return {
        "hidden_gem": "A local spot, not on the usual tourist trail.",
        "regional_food": "Local eatery.",
        "homestay": "Family-run accommodation.",
    }.get(category, "")


def fetch_live_places(lat: float, lng: float, radius_km: float = 15.0) -> list[dict] | None:
    """Real Discovery places from OpenStreetMap Overpass, or None if the API
    is disabled, unreachable, or times out -- callers must fall back to the
    database in that case, never invent a place. Cached briefly so repeated
    requests for the same neighbourhood don't hammer the public endpoint."""
    if not settings.DISCOVERY_LIVE_ENABLED:
        return None

    key = _cache_key(lat, lng, radius_km)
    cached = _cache.get(key)
    now = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    query = _OVERPASS_QUERY.format(
        timeout=int(settings.OVERPASS_TIMEOUT_SECONDS), radius_m=int(radius_km * 1000), lat=lat, lng=lng,
    )
    try:
        resp = httpx.post(
            settings.OVERPASS_API_URL, data={"data": query},
            headers={"User-Agent": "musafir-smart-tourist-safety/1.0 (discovery live lookup)"},
            timeout=settings.OVERPASS_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Overpass discovery request failed, falling back to database: %s", e)
        return cached[0] if cached else None

    places = []
    for el in elements:
        tags = el.get("tags", {})
        category = _element_category(tags)
        name = tags.get("name")
        if not category or not name:
            continue
        point = el.get("center") or el
        elat, elng = point.get("lat"), point.get("lon")
        if elat is None or elng is None:
            continue
        places.append({
            "id": f"osm:{el['id']}", "name": name, "category": category,
            "lat": elat, "lng": elng, "tip": _tip_from_tags(tags, category), "source": "osm",
        })

    _cache[key] = (places, now + settings.DISCOVERY_CACHE_TTL_SECONDS)
    return places


def _from_db(db: Session, lat: float, lng: float, radius_km: float, categories: list[str]) -> list[dict]:
    places = db.query(PointOfInterest).filter(PointOfInterest.category.in_(categories)).all()
    out = []
    for p in places:
        dist_km = haversine_m(lat, lng, p.lat, p.lng) / 1000
        if dist_km <= radius_km:
            out.append({
                "id": p.id, "name": p.name, "category": p.category,
                "lat": p.lat, "lng": p.lng, "tip": p.phone or "", "source": p.source,
            })
    return out


def find_discovery(
    db: Session, lat: float, lng: float, radius_km: float = 25.0,
    categories: list[str] | None = None,
) -> list[dict]:
    cats = [c for c in (categories or DISCOVERY_CATEGORIES) if c in DISCOVERY_CATEGORIES]
    if not cats:
        cats = list(DISCOVERY_CATEGORIES)

    live = fetch_live_places(lat, lng, radius_km)
    db_rows = _from_db(db, lat, lng, radius_km, cats)

    if live is None:
        merged = db_rows
    else:
        # Merge live OSM results with whatever's seeded/cached in the DB,
        # de-duplicating by name -- a place already in the database (e.g. a
        # curated seed row) shouldn't also show up as a duplicate OSM hit.
        live_in_cats = [p for p in live if p["category"] in cats]
        seen_names = {p["name"].strip().lower() for p in live_in_cats}
        merged = live_in_cats + [p for p in db_rows if p["name"].strip().lower() not in seen_names]

    for p in merged:
        p["distance_km"] = round(haversine_m(lat, lng, p["lat"], p["lng"]) / 1000, 2)
    merged.sort(key=lambda r: r["distance_km"])
    return merged


def offline_bundle(db: Session, lat: float, lng: float, radius_km: float = 25.0) -> dict:
    """Same data as find_discovery, wrapped with a generated_at timestamp so
    a cached copy on-device can show its own age when offline."""
    return {
        "generated_at": utc_now().isoformat(), "lat": lat, "lng": lng, "radius_km": radius_km,
        "places": find_discovery(db, lat, lng, radius_km),
    }


_INDOOR_QUERY = """
[out:json][timeout:{timeout}];
(
  node["tourism"="museum"](around:{radius_m},{lat},{lng});
  node["tourism"="gallery"](around:{radius_m},{lat},{lng});
  node["amenity"="arts_centre"](around:{radius_m},{lat},{lng});
  node["shop"="mall"](around:{radius_m},{lat},{lng});
);
out center tags;
"""

_indoor_cache: dict[tuple[float, float, float], tuple[list[dict], float]] = {}


def find_indoor_alternatives(lat: float, lng: float, radius_km: float = 15.0) -> list[dict]:
    """Real indoor attractions (museum/gallery/arts centre/mall) near a
    point, from OpenStreetMap Overpass -- used by the Smart Trip Planner to
    swap an outdoor day for a real indoor option on bad-weather days (see
    services/trip_planner.py), instead of just flagging the day as risky
    with nothing concrete to switch to. [] (never invented) on any failure."""
    if not settings.DISCOVERY_LIVE_ENABLED:
        return []
    key = _cache_key(lat, lng, radius_km)
    cached = _indoor_cache.get(key)
    now = time.monotonic()
    if cached and cached[1] > now:
        return cached[0]

    query = _INDOOR_QUERY.format(
        timeout=int(settings.OVERPASS_TIMEOUT_SECONDS), radius_m=int(radius_km * 1000), lat=lat, lng=lng,
    )
    try:
        resp = httpx.post(
            settings.OVERPASS_API_URL, data={"data": query},
            headers={"User-Agent": "musafir-smart-tourist-safety/1.0 (indoor alternative lookup)"},
            timeout=settings.OVERPASS_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Overpass indoor-alternative request failed: %s", e)
        return cached[0] if cached else []

    out = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        point = el.get("center") or el
        elat, elng = point.get("lat"), point.get("lon")
        if not name or elat is None or elng is None:
            continue
        out.append({
            "name": name, "lat": elat, "lng": elng,
            "distance_km": round(haversine_m(lat, lng, elat, elng) / 1000, 2),
        })
    out.sort(key=lambda r: r["distance_km"])
    _indoor_cache[key] = (out, now + settings.DISCOVERY_CACHE_TTL_SECONDS)
    return out


def clear_cache() -> None:
    _cache.clear()
    _indoor_cache.clear()
