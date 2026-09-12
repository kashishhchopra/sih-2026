"""Crowd & Queue Forecast (services/crowd_forecast.py, /crowd/forecast, /crowd/forecast/poi/{id})."""
from tests.conftest import make_poi, make_tourist, make_zone


def test_forecast_lists_every_zone_with_a_reason(client, admin_headers, db):
    make_zone(db, name="Zone A")
    r = client.get("/api/crowd/forecast", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert any(z["zone"] == "Zone A" for z in body)
    for z in body:
        assert z["reasons"]  # never a bare number with no explanation
        assert z["forecast_density"] in ("low", "medium", "high")


def test_holiday_name_absent_without_an_api_key(client, admin_headers, db):
    make_zone(db, name="Zone A")
    r = client.get("/api/crowd/forecast", headers=admin_headers)
    for z in r.json():
        # CALENDARIFIC_API_KEY is blank in tests -- never a fabricated holiday.
        assert z["holiday_name"] is None
        assert z["is_holiday_period"] is False


def test_more_tourists_in_a_zone_raises_its_current_density(client, admin_headers, db):
    zone = make_zone(db, name="Busy Zone", lat=26.165, lng=91.75, d=0.02)
    for i in range(20):
        make_tourist(db, name=f"T{i}", lat=26.165, lng=91.75)

    r = client.get("/api/crowd/forecast", headers=admin_headers)
    busy = next(z for z in r.json() if z["zone_id"] == zone.id)
    assert busy["tourist_count"] >= 20
    assert busy["current_density"] in ("medium", "high")


def test_queue_estimate_for_a_poi(client, admin_headers, db):
    poi = make_poi(db, name="Museum", category="hidden_gem", lat=26.1445, lng=91.7362)
    r = client.get(f"/api/crowd/forecast/poi/{poi.id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_wait_minutes"] > 0
    assert body["band"] in ("low", "medium", "high")


def test_queue_estimate_unknown_poi_404s(client, admin_headers):
    r = client.get("/api/crowd/forecast/poi/999999", headers=admin_headers)
    assert r.status_code == 404
