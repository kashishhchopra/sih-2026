"""Discovery (services/discovery.py, /discovery, /discovery/offline-bundle).

DISCOVERY_LIVE_ENABLED is forced off for the whole test run (see
conftest.py) so these never depend on the real Overpass API being reachable
-- they test the database-backed path, which is exactly what a request
falls back to when the live one is unavailable in production too.
"""
from tests.conftest import make_poi


def test_discovery_returns_seeded_places_within_radius(client, admin_headers, db):
    make_poi(db, name="Hidden Waterfall", category="hidden_gem", lat=26.1450, lng=91.7370)
    make_poi(db, name="Far Away Place", category="hidden_gem", lat=27.5, lng=93.5)  # way outside radius

    r = client.get("/api/discovery", headers=admin_headers, params={"lat": 26.1445, "lng": 91.7362, "radius_km": 10})
    assert r.status_code == 200
    names = [p["name"] for p in r.json()["places"]]
    assert "Hidden Waterfall" in names
    assert "Far Away Place" not in names


def test_discovery_category_filter(client, admin_headers, db):
    make_poi(db, name="Local Eatery", category="regional_food", lat=26.1450, lng=91.7370)
    make_poi(db, name="Family Homestay", category="homestay", lat=26.1450, lng=91.7370)

    r = client.get("/api/discovery", headers=admin_headers,
                   params={"lat": 26.1445, "lng": 91.7362, "radius_km": 10, "categories": "homestay"})
    places = r.json()["places"]
    assert all(p["category"] == "homestay" for p in places)
    assert any(p["name"] == "Family Homestay" for p in places)


def test_discovery_places_are_sorted_nearest_first(client, admin_headers, db):
    make_poi(db, name="Near", category="hidden_gem", lat=26.1450, lng=91.7370)
    make_poi(db, name="Farther", category="hidden_gem", lat=26.2000, lng=91.8000)

    r = client.get("/api/discovery", headers=admin_headers, params={"lat": 26.1445, "lng": 91.7362, "radius_km": 50})
    places = r.json()["places"]
    distances = [p["distance_km"] for p in places]
    assert distances == sorted(distances)


def test_offline_bundle_carries_a_generated_timestamp(client, admin_headers, db):
    make_poi(db, name="Somewhere", category="regional_food", lat=26.1450, lng=91.7370)
    r = client.get("/api/discovery/offline-bundle", headers=admin_headers,
                   params={"lat": 26.1445, "lng": 91.7362, "radius_km": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["generated_at"]
    assert isinstance(body["places"], list)


def test_live_lookup_disabled_returns_none_not_an_error():
    from app.services.discovery import fetch_live_places

    assert fetch_live_places(26.1445, 91.7362) is None
