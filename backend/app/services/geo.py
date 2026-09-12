"""Geospatial helpers: haversine distance, point-in-polygon, route deviation."""
import json
import math
from functools import lru_cache

from shapely.geometry import Point, Polygon

from app.models.zone import Zone

EARTH_RADIUS_M = 6_371_000.0


def zone_centroid(zone: Zone) -> tuple[float, float] | None:
    """Plain average of a zone's polygon vertices -- good enough for "roughly
    where this zone is" (weather lookups, map pin placement for an
    area-level advisory), not a true geometric centroid. Returns None for a
    zone with no/empty polygon."""
    try:
        points = json.loads(zone.polygon or "[]")
    except (ValueError, TypeError):
        return None
    if not points:
        return None
    lat = sum(p[0] for p in points) / len(points)
    lng = sum(p[1] for p in points) / len(points)
    return (lat, lng)


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@lru_cache(maxsize=512)
def _compiled_polygon(zone_id: int, polygon_json: str) -> Polygon | None:
    """Parse+build a shapely Polygon once per (zone, geometry) pair.

    `process_ping` calls `zones_containing_point` on every single GPS ping, which
    used to re-parse the stored JSON and reconstruct a shapely Polygon from
    scratch on every call, for every zone, on every ping -- pure waste, since a
    zone's geometry almost never changes between pings. Keying the cache on the
    polygon's own JSON (not just the zone id) means an edited zone gets a fresh
    cache entry for free, with no invalidation bookkeeping needed.
    """
    verts = json.loads(polygon_json)
    if len(verts) < 3:
        return None
    # shapely uses (x=lng, y=lat)
    return Polygon([(v[1], v[0]) for v in verts])


def point_in_zone(lat: float, lng: float, zone: Zone) -> bool:
    """Point-in-polygon test using a cached, pre-built shapely Polygon."""
    poly = _compiled_polygon(zone.id, zone.polygon)
    if poly is None:
        return False
    return poly.contains(Point(lng, lat))


def clear_polygon_cache() -> None:
    """Drop cached polygons. Used by tests and after bulk zone edits."""
    _compiled_polygon.cache_clear()


def zones_containing_point(lat: float, lng: float, zones: list[Zone]) -> list[Zone]:
    return [z for z in zones if point_in_zone(lat, lng, z)]


def zones_intersecting_polygon(coords: list[list[float]], zones: list[Zone]) -> list[Zone]:
    """Zones whose geometry overlaps an externally-sourced polygon (e.g. a
    CAP disaster-advisory area, see services/cap.py) -- used to translate a
    free-standing geographic advisory into the zone_id-scoped candidates
    services/disaster.py already knows how to create/expire/notify on.
    `coords` are [lat, lng] pairs, matching Zone.polygon's own convention.
    """
    if len(coords) < 3:
        return []
    advisory_poly = Polygon([(lng, lat) for lat, lng in coords])
    if not advisory_poly.is_valid:
        advisory_poly = advisory_poly.buffer(0)  # common fix for a self-intersecting ring
    out = []
    for z in zones:
        zone_poly = _compiled_polygon(z.id, z.polygon)
        if zone_poly is not None and zone_poly.intersects(advisory_poly):
            out.append(z)
    return out


def min_distance_to_route(lat: float, lng: float, itinerary: list[dict]) -> float:
    """Minimum distance (m) from a point to any planned itinerary waypoint.

    A simple, explainable proxy for route-deviation: if the tourist strays
    further than a threshold from every planned stop, they've deviated.
    """
    if not itinerary:
        return 0.0
    return min(haversine_m(lat, lng, wp["lat"], wp["lng"]) for wp in itinerary)
