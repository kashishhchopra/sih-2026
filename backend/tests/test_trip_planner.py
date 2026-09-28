"""Smart Trip Planner (services/trip_planner.py, /tourists/{id}/trip-plan)."""
from datetime import timedelta

from app.core.time import utc_now
from tests.conftest import make_tourist, make_zone


def test_plan_distributes_itinerary_across_days(client, admin_headers, db):
    now = utc_now()
    t = make_tourist(
        db, itinerary=[
            {"name": "Stop A", "lat": 26.14, "lng": 91.73},
            {"name": "Stop B", "lat": 26.16, "lng": 91.75},
            {"name": "Stop C", "lat": 26.18, "lng": 91.77},
            {"name": "Stop D", "lat": 26.20, "lng": 91.79},
        ],
        trip_start=now, trip_end=now + timedelta(days=1),  # 2-day trip, 4 stops
    )
    r = client.get(f"/api/tourists/{t.id}/trip-plan", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body["days"]) == 2
    all_stops = [s["name"] for d in body["days"] for s in d["stops"]]
    assert set(all_stops) == {"Stop A", "Stop B", "Stop C", "Stop D"}


def test_plan_with_no_itinerary_says_so_instead_of_fabricating_one(client, admin_headers, db):
    t = make_tourist(db, itinerary=[])
    r = client.get(f"/api/tourists/{t.id}/trip-plan", headers=admin_headers)
    body = r.json()
    assert body["days"] == []
    assert any("no confirmed itinerary" in n.lower() for n in body["notes"])


def test_days_query_param_is_bounded(client, admin_headers, db):
    t = make_tourist(db, itinerary=[{"name": "Stop A", "lat": 26.14, "lng": 91.73}])
    r = client.get(f"/api/tourists/{t.id}/trip-plan", headers=admin_headers, params={"days": 999})
    assert r.status_code == 422  # over the ge/le=14 bound


def test_permit_flag_appears_for_a_stop_inside_a_restricted_zone(client, admin_headers, db):
    make_zone(db, name="Restricted Zone", risk="restricted", lat=26.14, lng=91.73, d=0.05)
    t = make_tourist(db, itinerary=[{"name": "Border Post", "lat": 26.14, "lng": 91.73}])
    r = client.get(f"/api/tourists/{t.id}/trip-plan", headers=admin_headers)
    day = r.json()["days"][0]
    assert "restricted_area_permit" in day["permits_suggested"]


def test_unknown_tourist_404s(client, admin_headers):
    r = client.get("/api/tourists/999999/trip-plan", headers=admin_headers)
    assert r.status_code == 404
