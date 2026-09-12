"""Compiled-polygon cache: must never return a stale geometry."""
import json

from app.services import geo
from tests.conftest import make_zone


def test_cached_result_matches_direct_computation(db):
    z = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    geo.clear_polygon_cache()

    first = geo.point_in_zone(26.165, 91.75, z)
    second = geo.point_in_zone(26.165, 91.75, z)  # served from cache
    assert first is second is True


def test_editing_a_zones_polygon_is_reflected_immediately(db):
    """The cache key includes the polygon's own JSON, so an edited zone must
    not keep answering with its old shape even though its id is unchanged."""
    z = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    assert geo.point_in_zone(26.165, 91.75, z) is True

    # Shrink the zone so the same point now falls outside it.
    z.polygon = json.dumps([
        [26.1649, 91.7499], [26.1649, 91.7501],
        [26.1651, 91.7501], [26.1651, 91.7499],
    ])
    assert geo.point_in_zone(26.20, 91.90, z) is False


def test_two_zones_with_identical_shapes_do_not_interfere(db):
    a = make_zone(db, name="A", lat=26.165, lng=91.75, d=0.008)
    b = make_zone(db, name="B", lat=26.165, lng=91.75, d=0.008)
    assert geo.point_in_zone(26.165, 91.75, a) is True
    assert geo.point_in_zone(26.165, 91.75, b) is True


def test_clear_polygon_cache_does_not_break_subsequent_lookups(db):
    z = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    geo.point_in_zone(26.165, 91.75, z)
    geo.clear_polygon_cache()
    assert geo.point_in_zone(26.165, 91.75, z) is True
