"""Trajectory prediction: kinematic extrapolation + zone-crossing lookahead."""
from datetime import timedelta

from app.core.time import utc_now
from app.models.tourist import LocationPing
from app.services.geo import haversine_m
from app.services.trajectory import predict_trajectory, predicts_crosses_zone
from tests.conftest import make_zone


def _ping(lat, lng, minutes_ago):
    return LocationPing(
        tourist_id=1, lat=lat, lng=lng, speed_kmh=10,
        timestamp=utc_now() - timedelta(minutes=minutes_ago),
    )


def _straight_line_pings():
    """A tourist walking steadily north-east, one ping per minute."""
    base_lat, base_lng = 26.1000, 91.7000
    step = 0.001  # ~110m per step
    return [
        _ping(base_lat + i * step, base_lng + i * step, minutes_ago=4 - i)
        for i in range(5)
    ]


def test_extrapolation_continues_in_the_same_direction():
    pings = _straight_line_pings()
    points = predict_trajectory(pings, horizon_min=15)

    assert len(points) == 3  # steps at 5, 10, 15 minutes
    last = pings[-1]
    prev_dist = 0.0
    for lat, lng, eta_min in points:
        assert eta_min in (5.0, 10.0, 15.0)
        # continuing north-east: both lat and lng should have increased
        assert lat > last.lat
        assert lng > last.lng
        dist = haversine_m(last.lat, last.lng, lat, lng)
        assert dist > prev_dist  # farther out for a larger eta
        prev_dist = dist


def test_sane_distance_for_the_observed_speed():
    pings = _straight_line_pings()
    points = predict_trajectory(pings, horizon_min=5)
    assert len(points) == 1
    lat, lng, eta_min = points[0]
    last = pings[-1]
    dist_m = haversine_m(last.lat, last.lng, lat, lng)
    # ~110m/min observed -> ~550m in 5 minutes, generously bounded
    assert 200 < dist_m < 1200


def test_zero_pings_returns_empty():
    assert predict_trajectory([], horizon_min=15) == []


def test_one_ping_returns_empty():
    assert predict_trajectory([_ping(26.10, 91.70, 0)], horizon_min=15) == []


def test_stationary_tourist_returns_empty():
    pings = [_ping(26.10, 91.70, minutes_ago=m) for m in (4, 3, 2, 1, 0)]
    assert predict_trajectory(pings, horizon_min=15) == []


def test_non_positive_horizon_returns_empty():
    pings = _straight_line_pings()
    assert predict_trajectory(pings, horizon_min=0) == []


def test_predicts_crosses_zone_detects_a_zone_directly_ahead(db):
    pings = _straight_line_pings()
    points = predict_trajectory(pings, horizon_min=15)
    ahead_lat, ahead_lng, _ = points[-1]
    zone = make_zone(db, name="Ahead Zone", risk="high", lat=ahead_lat, lng=ahead_lng, d=0.002)

    hit = predicts_crosses_zone(points, [zone])
    assert hit is not None
    assert hit["zone"].id == zone.id
    assert hit["eta_min"] > 0


def test_predicts_crosses_zone_ignores_a_zone_behind(db):
    pings = _straight_line_pings()
    points = predict_trajectory(pings, horizon_min=15)
    last = pings[-1]
    # place the zone well behind the direction of travel (south-west of start)
    behind_zone = make_zone(db, name="Behind Zone", risk="high",
                            lat=last.lat - 0.05, lng=last.lng - 0.05, d=0.002)

    assert predicts_crosses_zone(points, [behind_zone]) is None


def test_predicts_crosses_zone_ignores_low_and_medium_risk(db):
    pings = _straight_line_pings()
    points = predict_trajectory(pings, horizon_min=15)
    ahead_lat, ahead_lng, _ = points[-1]
    zone = make_zone(db, name="Ahead Low Zone", risk="low", lat=ahead_lat, lng=ahead_lng, d=0.002)

    assert predicts_crosses_zone(points, [zone]) is None
