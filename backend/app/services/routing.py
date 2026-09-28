"""Lightweight in-repo "safe route" candidate generator.

There is no road-network routing engine (OSRM or similar) anywhere in this
codebase, and standing one up is out of scope here. Instead this generates a
handful of straight-segment candidate polylines between an origin and
destination -- the direct line plus small lateral perturbations -- scores
each by the zone risk sampled along it, and recommends the lowest-risk one.
This is deliberately NOT turn-by-turn navigation; callers (the API layer,
the frontend) are expected to say so explicitly.
"""
from __future__ import annotations

import math

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.zone import Zone
from app.services.geo import EARTH_RADIUS_M, haversine_m, zones_containing_point
from app.services.safety import _RISK_WEIGHT

# Fixed thresholds on the per-km risk score (see `_route_length_km` below for
# what "risk score" means) rather than relative ranking against sibling
# candidates -- keeps a single candidate's risk_level meaningful even when
# `recommend_route` is asked about just one route, and keeps the bucket
# boundaries visible/tunable in one place instead of scattered logic.
_RISK_LEVEL_THRESHOLDS = (("low", 15.0), ("medium", 40.0), ("high", 70.0))


def _bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial bearing (degrees, 0-360, 0=north) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


def _project(lat: float, lng: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Destination point `dist_m` metres from (lat, lng) along `bearing_deg`."""
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    ang = dist_m / EARTH_RADIUS_M
    lat2 = math.asin(
        math.sin(lat1) * math.cos(ang) + math.cos(lat1) * math.sin(ang) * math.cos(br)
    )
    lng2 = lng1 + math.atan2(
        math.sin(br) * math.sin(ang) * math.cos(lat1),
        math.cos(ang) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), (math.degrees(lng2) + 540) % 360 - 180


def _midpoint(lat1: float, lng1: float, lat2: float, lng2: float) -> tuple[float, float]:
    """Simple average midpoint -- fine at the short distances routes here span."""
    return (lat1 + lat2) / 2.0, (lng1 + lng2) / 2.0


def _offset_waypoints(
    origin: tuple[float, float], destination: tuple[float, float], side: int, offset_m: float
) -> list[tuple[float, float]]:
    """Origin, one midpoint nudged perpendicular to the origin->destination
    bearing by `offset_m` metres (left if side<0, right if side>0), destination."""
    olat, olng = origin
    dlat, dlng = destination
    bearing = _bearing_deg(olat, olng, dlat, dlng)
    perp_bearing = (bearing + 90 * (1 if side > 0 else -1)) % 360
    mlat, mlng = _midpoint(olat, olng, dlat, dlng)
    olat2, olng2 = _project(mlat, mlng, perp_bearing, offset_m)
    return [origin, (olat2, olng2), destination]


def _route_length_km(points: list[tuple[float, float]]) -> float:
    return sum(
        haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:], strict=False)
    ) / 1000.0


def _sample_points(
    points: list[tuple[float, float]], interval_m: float
) -> list[tuple[float, float]]:
    """Sample points every `interval_m` metres along the polyline (plus the
    final vertex), walking each straight segment in turn."""
    if len(points) < 2:
        return list(points)
    samples: list[tuple[float, float]] = [points[0]]
    for a, b in zip(points, points[1:], strict=False):
        seg_len = haversine_m(a[0], a[1], b[0], b[1])
        if seg_len <= 0:
            continue
        n_steps = max(1, int(seg_len // interval_m))
        for i in range(1, n_steps + 1):
            frac = min(i * interval_m / seg_len, 1.0)
            lat = a[0] + (b[0] - a[0]) * frac
            lng = a[1] + (b[1] - a[1]) * frac
            samples.append((lat, lng))
    return samples


def _score_route(db: Session, points: list[tuple[float, float]], zones: list[Zone]) -> dict:
    length_km = _route_length_km(points)
    samples = _sample_points(points, settings.ROUTE_SAMPLE_INTERVAL_M)
    total_risk = 0.0
    for lat, lng in samples:
        inside = zones_containing_point(lat, lng, zones)
        if inside:
            worst = max(inside, key=lambda z: _RISK_WEIGHT.get(z.risk_level, 50))
            total_risk += _RISK_WEIGHT.get(worst.risk_level, 50)
    # Normalize by sample count so a longer route (more samples) isn't
    # unfairly penalized purely for having more points -- this yields an
    # average per-sample risk, comparable across candidates of any length.
    risk_score = total_risk / len(samples) if samples else 0.0
    return {
        "points": [[lat, lng] for lat, lng in points],
        "risk_score": round(risk_score, 2),
        "length_km": round(length_km, 3),
    }


def candidate_routes(
    db: Session, origin: tuple[float, float], destination: tuple[float, float]
) -> list[dict]:
    """Generate the direct line plus two laterally-offset variants, score each
    by average zone risk along it, and return them sorted best (lowest
    risk_score, ties broken by shorter length) first.

    Degenerate case (origin == destination): a single zero-length "route" at
    that point, since there is nowhere to route to.
    """
    zones = db.query(Zone).all()
    offset_m = settings.ROUTE_CANDIDATE_OFFSET_M

    if origin == destination:
        return [_score_route(db, [origin, destination], zones)]

    raw_candidates = [
        [origin, destination],
        _offset_waypoints(origin, destination, side=-1, offset_m=offset_m),
        _offset_waypoints(origin, destination, side=1, offset_m=offset_m),
    ]
    scored = [_score_route(db, pts, zones) for pts in raw_candidates]
    scored.sort(key=lambda c: (c["risk_score"], c["length_km"]))
    return scored


def _risk_level_for(risk_score: float) -> str:
    for level, ceiling in _RISK_LEVEL_THRESHOLDS:
        if risk_score <= ceiling:
            return level
    return "restricted"


def recommend_route(
    db: Session, origin: tuple[float, float], destination: tuple[float, float]
) -> dict:
    """Top pick (lowest risk_score) plus the full list of scored candidates,
    each tagged with a `risk_level` bucket derived from fixed thresholds on
    its per-sample average risk score (see `_RISK_LEVEL_THRESHOLDS`)."""
    candidates = candidate_routes(db, origin, destination)
    for c in candidates:
        c["risk_level"] = _risk_level_for(c["risk_score"])
    return {"recommended": candidates[0], "candidates": candidates}
