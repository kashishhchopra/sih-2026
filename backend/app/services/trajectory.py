"""Short-horizon trajectory prediction from recent GPS ping history.

Simple kinematic extrapolation (average bearing + average speed over the
last few pings), not a learned model -- deliberately explainable, and cheap
enough to run on every ping alongside the existing geofence check.
"""
from __future__ import annotations

import math

from app.models.tourist import LocationPing
from app.models.zone import Zone
from app.services.geo import EARTH_RADIUS_M, haversine_m, zones_containing_point

# How many of the most recent pings feed the bearing/speed estimate. More than
# this and old, possibly stale direction changes would drown out where the
# tourist is heading *right now*.
_MAX_HISTORY = 5
# Emit a predicted point every 5 simulated minutes out to the horizon.
_STEP_MIN = 5.0


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


def predict_trajectory(
    pings: list[LocationPing], horizon_min: float
) -> list[tuple[float, float, float]]:
    """Extrapolate future positions from recent ping history.

    `pings` is expected oldest-first. Returns a list of (lat, lng, eta_min)
    points at even time steps out to `horizon_min`. Returns [] whenever there
    isn't enough signal to extrapolate from: fewer than 2 pings, a
    non-positive horizon, or a tourist who hasn't actually moved (average
    speed ~0 -- bearing is undefined and there's nowhere for them to project
    toward).
    """
    if len(pings) < 2 or horizon_min <= 0:
        return []

    recent = pings[-_MAX_HISTORY:]
    dists, bearings, dts = [], [], []
    for a, b in zip(recent, recent[1:], strict=False):
        dt_s = (b.timestamp - a.timestamp).total_seconds()
        if dt_s <= 0:
            continue
        d = haversine_m(a.lat, a.lng, b.lat, b.lng)
        dists.append(d)
        dts.append(dt_s)
        if d > 1e-3:  # bearing is undefined over a stationary segment
            bearings.append(_bearing_deg(a.lat, a.lng, b.lat, b.lng))

    if not dts or not bearings:
        return []

    speed_mps = sum(dists) / sum(dts)
    if speed_mps < 1e-3:
        return []

    # Circular mean so e.g. 350deg and 10deg average to 0deg, not 180deg.
    sin_sum = sum(math.sin(math.radians(b)) for b in bearings)
    cos_sum = sum(math.cos(math.radians(b)) for b in bearings)
    avg_bearing = math.degrees(math.atan2(sin_sum, cos_sum)) % 360

    last = recent[-1]
    points: list[tuple[float, float, float]] = []
    t = _STEP_MIN
    while t <= horizon_min + 1e-9:
        dist_m = speed_mps * t * 60.0
        plat, plng = _project(last.lat, last.lng, avg_bearing, dist_m)
        points.append((plat, plng, t))
        t += _STEP_MIN
    return points


_ZONE_RANK = {"low": 0, "medium": 1, "high": 2, "restricted": 3}


def predicts_crosses_zone(
    predicted_points: list[tuple[float, float, float]], zones: list[Zone]
) -> dict | None:
    """First high-risk/restricted zone a predicted point falls inside.

    Returns {"zone": Zone, "eta_min": float} for the earliest (soonest-ETA)
    hit, or None if the projected path never crosses one.
    """
    for lat, lng, eta_min in predicted_points:
        hits = zones_containing_point(lat, lng, zones)
        risky = [z for z in hits if z.risk_level in ("high", "restricted")]
        if risky:
            worst = max(risky, key=lambda z: _ZONE_RANK.get(z.risk_level, 0))
            return {"zone": worst, "eta_min": eta_min}
    return None
