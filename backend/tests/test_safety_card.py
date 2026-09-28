"""Offline Maps & Safety Card (services/safety_card.py, /tourists/{id}/safety-card)."""
from tests.conftest import make_poi, make_tourist, make_unit


def test_safety_card_includes_emergency_numbers(client, admin_headers, db):
    t = make_tourist(db)
    r = client.get(f"/api/tourists/{t.id}/safety-card", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["emergency_numbers"]["all_in_one"] == "112"
    assert body["nearest_hospital"] is None
    assert body["nearest_police"] is None
    assert body["nearest_pharmacy"] is None
    assert body["nearest_transport"] is None


def test_safety_card_finds_nearest_pharmacy_and_transport(client, admin_headers, db):
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    make_poi(db, name="City Pharmacy", category="pharmacy", lat=26.145, lng=91.737, phone="100")
    make_poi(db, name="Main Bus Stand", category="bus_stop", lat=26.146, lng=91.738)

    r = client.get(f"/api/tourists/{t.id}/safety-card", headers=admin_headers)
    body = r.json()
    assert body["nearest_pharmacy"]["name"] == "City Pharmacy"
    assert body["nearest_pharmacy"]["phone"] == "100"
    assert body["nearest_transport"]["name"] == "Main Bus Stand"
    assert body["nearest_transport"]["category"] == "bus_stop"


def test_safety_card_finds_nearest_units(client, admin_headers, db):
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    make_unit(db, name="City Hospital", unit_type="ambulance", lat=26.145, lng=91.737)
    make_unit(db, name="Central PS", unit_type="police", lat=26.146, lng=91.738)

    r = client.get(f"/api/tourists/{t.id}/safety-card", headers=admin_headers)
    body = r.json()
    assert body["nearest_hospital"]["name"] == "City Hospital"
    assert body["nearest_police"]["name"] == "Central PS"
    assert body["nearest_hospital"]["distance_km"] >= 0


def test_safety_card_visible_to_self(client, tourist_headers, tourist_user):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/safety-card", headers=tourist_headers)
    assert r.status_code == 200


def test_safety_card_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Not Me")
    r = client.get(f"/api/tourists/{other.id}/safety-card", headers=tourist_headers)
    assert r.status_code == 403


def test_safety_card_omits_consular_info_for_indian_nationals(client, admin_headers, db):
    t = make_tourist(db)  # default nationality="Indian"
    r = client.get(f"/api/tourists/{t.id}/safety-card", headers=admin_headers)
    assert "consular" not in r.json()


def test_safety_card_includes_consular_info_for_foreign_nationals(client, admin_headers, db):
    t = make_tourist(db)
    t.nationality = "Japanese"
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/safety-card", headers=admin_headers)
    body = r.json()
    assert body["consular"]["country_code"] == "JP"
    assert body["country_guidance"]["helpline_language"] == "Japanese"


def test_safety_card_unrecognised_nationality_has_no_consular_info(client, admin_headers, db):
    t = make_tourist(db)
    t.nationality = "Atlantean"
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/safety-card", headers=admin_headers)
    assert "consular" not in r.json()
