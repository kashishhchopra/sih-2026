"""Geospatial helpers. These underpin geofencing and route-deviation alerts."""
import json

import pytest

from app.services.geo import (
    haversine_m,
    min_distance_to_route,
    point_in_zone,
    zones_containing_point,
)
from tests.conftest import make_zone


def test_haversine_zero_distance():
    assert haversine_m(26.1445, 91.7362, 26.1445, 91.7362) == pytest.approx(0, abs=1e-6)


def test_haversine_known_distance():
    """Guwahati -> Shillong is roughly 82 km great-circle."""
    d = haversine_m(26.1445, 91.7362, 25.5788, 91.8933)
    assert d == pytest.approx(64_000, rel=0.15)


def test_haversine_one_degree_of_latitude_is_about_111km():
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_195, rel=0.01)


def test_haversine_is_symmetric():
    a = haversine_m(26.1, 91.7, 26.2, 91.8)
    b = haversine_m(26.2, 91.8, 26.1, 91.7)
    assert a == pytest.approx(b)


def test_point_inside_zone(db):
    z = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    assert point_in_zone(26.165, 91.75, z) is True


def test_point_outside_zone(db):
    z = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    assert point_in_zone(26.20, 91.90, z) is False


def test_degenerate_polygon_contains_nothing(db):
    z = make_zone(db)
    z.polygon = json.dumps([[26.1, 91.7], [26.2, 91.8]])  # only two vertices
    db.commit()
    assert point_in_zone(26.15, 91.75, z) is False


def test_zones_containing_point_finds_overlaps(db):
    a = make_zone(db, name="Inner", lat=26.165, lng=91.75, d=0.004)
    b = make_zone(db, name="Outer", lat=26.165, lng=91.75, d=0.02)
    far = make_zone(db, name="Far", lat=27.5, lng=92.5, d=0.01)

    names = {z.name for z in zones_containing_point(26.165, 91.75, [a, b, far])}
    assert names == {"Inner", "Outer"}


def test_min_distance_to_route_empty_itinerary_is_zero():
    """No plan means no deviation -- must not raise on an empty list."""
    assert min_distance_to_route(26.1, 91.7, []) == 0.0


def test_min_distance_to_route_picks_nearest_waypoint():
    itinerary = [
        {"name": "Far", "lat": 27.0, "lng": 92.0},
        {"name": "Near", "lat": 26.1450, "lng": 91.7365},
    ]
    d = min_distance_to_route(26.1445, 91.7362, itinerary)
    assert d < 100


def test_min_distance_to_route_detects_deviation():
    itinerary = [{"name": "Plan", "lat": 26.1445, "lng": 91.7362}]
    assert min_distance_to_route(26.30, 91.90, itinerary) > 2000


# ---------------------------------------------------------------- zones_intersecting_polygon
def test_zones_intersecting_polygon_finds_overlap(db):
    from app.services.geo import zones_intersecting_polygon
    from tests.conftest import make_zone

    zone = make_zone(db, name="Target", lat=26.165, lng=91.75, d=0.02)
    advisory_polygon = [[26.10, 91.65], [26.10, 91.85], [26.25, 91.85], [26.25, 91.65]]

    matches = zones_intersecting_polygon(advisory_polygon, [zone])
    assert matches == [zone]


def test_zones_intersecting_polygon_excludes_non_overlapping_zones(db):
    from app.services.geo import zones_intersecting_polygon
    from tests.conftest import make_zone

    far_zone = make_zone(db, name="Far Away", lat=10.0, lng=70.0, d=0.01)
    advisory_polygon = [[26.10, 91.65], [26.10, 91.85], [26.25, 91.85], [26.25, 91.65]]

    assert zones_intersecting_polygon(advisory_polygon, [far_zone]) == []


def test_zones_intersecting_polygon_handles_a_degenerate_polygon():
    from app.services.geo import zones_intersecting_polygon

    assert zones_intersecting_polygon([[26.1, 91.7], [26.2, 91.8]], []) == []
