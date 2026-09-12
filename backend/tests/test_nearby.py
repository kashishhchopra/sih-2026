"""Nearby-resource discovery (services/nearby.py, GET /tourists/{id}/nearby)."""
from tests.conftest import make_poi, make_tourist, make_unit


def test_find_nearby_hospital_from_police_unit(client, admin_headers, db):
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    make_unit(db, name="City Hospital", unit_type="ambulance", lat=26.145, lng=91.737)

    r = client.get(f"/api/tourists/{t.id}/nearby?category=hospital", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "City Hospital"
    assert body[0]["directions_url"].startswith("https://www.google.com/maps/dir/")


def test_find_nearby_sorted_by_distance(client, admin_headers, db):
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    make_poi(db, name="Far Pharmacy", category="pharmacy", lat=26.17, lng=91.76)
    make_poi(db, name="Near Pharmacy", category="pharmacy", lat=26.145, lng=91.737)

    r = client.get(f"/api/tourists/{t.id}/nearby?category=pharmacy&radius_m=10000",
                   headers=admin_headers)
    names = [p["name"] for p in r.json()]
    assert names == ["Near Pharmacy", "Far Pharmacy"]


def test_find_nearby_respects_radius(client, admin_headers, db):
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    make_poi(db, name="Far Bus Stop", category="bus_stop", lat=27.0, lng=92.0)

    r = client.get(f"/api/tourists/{t.id}/nearby?category=transport&radius_m=1000", headers=admin_headers)
    assert r.json() == []


def test_find_nearby_invalid_category_rejected(client, admin_headers, db):
    t = make_tourist(db)
    r = client.get(f"/api/tourists/{t.id}/nearby?category=restaurant", headers=admin_headers)
    assert r.status_code == 400


def test_find_nearby_no_location_returns_empty(client, admin_headers, db):
    t = make_tourist(db)
    t.last_lat = None
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/nearby?category=hospital", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_find_nearby_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Not Me")
    r = client.get(f"/api/tourists/{other.id}/nearby?category=hospital", headers=tourist_headers)
    assert r.status_code == 403
