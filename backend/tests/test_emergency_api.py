"""SOS live-location sharing API (app/api/emergency.py)."""
import pytest

from app.models.incident import Incident
from app.models.tourist import Tourist
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


@pytest.fixture
def sos_incident(db, tourist_user):
    """An active SOS for the same tourist `tourist_headers` authenticates
    as, so the fixture and the auth fixture always agree on who "self" is."""
    make_unit(db)
    t = db.get(Tourist, tourist_user.tourist_id)
    result = trigger_sos(db, t, 26.1445, 91.7362, "help")
    return db.get(Incident, result["incident_id"])


def _loc(lat=26.15, lng=91.74, **kw):
    return {"lat": lat, "lng": lng, **kw}


# ---------------------------------------------------------------- posting
def test_tourist_can_post_their_own_emergency_location(client, tourist_headers, sos_incident):
    r = client.post(f"/api/incidents/{sos_incident.id}/location",
                    json=_loc(accuracy_m=8, speed_kmh=3.2, heading_deg=92), headers=tourist_headers)
    assert r.status_code == 201


def test_other_tourist_cannot_post_to_someone_elses_incident(client, db, sos_incident):
    from app.core.security import hash_password
    from app.models.user import User

    other_tourist = make_tourist(db, name="Someone Else")
    u = User(email="other@test.com", full_name="Someone Else",
             hashed_password=hash_password("otherpass1"), role="tourist", tourist_id=other_tourist.id)
    db.add(u)
    db.commit()
    r = client.post("/api/auth/login", data={"username": "other@test.com", "password": "otherpass1"})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post(f"/api/incidents/{sos_incident.id}/location", json=_loc(), headers=headers)
    assert r.status_code == 403


def test_admin_can_post_on_behalf_of_an_incident(client, admin_headers, sos_incident):
    r = client.post(f"/api/incidents/{sos_incident.id}/location", json=_loc(), headers=admin_headers)
    assert r.status_code == 201


def test_posting_to_an_unknown_incident_404s(client, tourist_headers):
    r = client.post("/api/incidents/999999/location", json=_loc(), headers=tourist_headers)
    assert r.status_code == 404


def test_rejects_invalid_latitude(client, tourist_headers, sos_incident):
    r = client.post(f"/api/incidents/{sos_incident.id}/location",
                    json=_loc(lat=999), headers=tourist_headers)
    assert r.status_code == 422


def test_rejects_missing_incident_id_route(client, tourist_headers):
    # No incident id at all -- FastAPI's own routing 404s/405s, never a crash.
    r = client.post("/api/incidents//location", json=_loc(), headers=tourist_headers)
    assert r.status_code in (404, 405)


def test_posting_after_tourist_stopped_tracking_is_rejected(client, tourist_headers, sos_incident):
    client.post(f"/api/incidents/{sos_incident.id}/stop-tracking", headers=tourist_headers)
    r = client.post(f"/api/incidents/{sos_incident.id}/location", json=_loc(), headers=tourist_headers)
    assert r.status_code == 409


def test_posting_to_a_resolved_incident_is_rejected(client, admin_headers, tourist_headers, sos_incident):
    client.patch(f"/api/incidents/{sos_incident.id}", json={"status": "resolved"}, headers=admin_headers)
    r = client.post(f"/api/incidents/{sos_incident.id}/location", json=_loc(), headers=tourist_headers)
    assert r.status_code == 409


def test_resolving_an_incident_stops_live_tracking(client, admin_headers, sos_incident, db):
    client.patch(f"/api/incidents/{sos_incident.id}", json={"status": "resolved"}, headers=admin_headers)
    db.refresh(sos_incident)
    assert sos_incident.live_tracking_active is False


# ---------------------------------------------------------------- reading
def test_admin_can_read_the_live_track(client, admin_headers, tourist_headers, sos_incident):
    client.post(f"/api/incidents/{sos_incident.id}/location",
               json=_loc(accuracy_m=8, speed_kmh=3.2, heading_deg=92), headers=tourist_headers)
    r = client.get(f"/api/incidents/{sos_incident.id}/location", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["latest"]["lat"] == 26.15
    assert body["location_status"] == "live"
    assert body["tourist_id"] == sos_incident.tourist_id


def test_responder_can_read_the_live_track(client, responder_headers, sos_incident):
    r = client.get(f"/api/incidents/{sos_incident.id}/location", headers=responder_headers)
    assert r.status_code == 200


def test_tourist_cannot_read_the_police_live_track_endpoint(client, tourist_headers, sos_incident):
    """This endpoint is police/responder-only -- a tourist reads their own
    status through their own SOS confirmation UI, never this route."""
    r = client.get(f"/api/incidents/{sos_incident.id}/location", headers=tourist_headers)
    assert r.status_code == 403


def test_unauthenticated_request_is_rejected(client, sos_incident):
    r = client.get(f"/api/incidents/{sos_incident.id}/location")
    assert r.status_code == 401


# ---------------------------------------------------------------- live list
def test_live_emergencies_list_is_police_only(client, tourist_headers):
    r = client.get("/api/incidents/live", headers=tourist_headers)
    assert r.status_code == 403


def test_live_emergencies_list_shows_active_incidents(client, admin_headers, sos_incident):
    r = client.get("/api/incidents/live", headers=admin_headers)
    assert r.status_code == 200
    ids = [e["incident_id"] for e in r.json()]
    assert sos_incident.id in ids


def test_multiple_simultaneous_emergencies_all_appear(client, admin_headers, db):
    make_unit(db)
    t1 = make_tourist(db, name="Tourist One")
    t2 = make_tourist(db, name="Tourist Two")
    r1 = trigger_sos(db, t1, 26.14, 91.73, "help")
    r2 = trigger_sos(db, t2, 26.20, 91.80, "help")

    r = client.get("/api/incidents/live", headers=admin_headers)
    ids = {e["incident_id"] for e in r.json()}
    assert {r1["incident_id"], r2["incident_id"]}.issubset(ids)


# ---------------------------------------------------------------- stop-tracking
def test_tourist_can_stop_their_own_tracking(client, tourist_headers, sos_incident, db):
    r = client.post(f"/api/incidents/{sos_incident.id}/stop-tracking", headers=tourist_headers)
    assert r.status_code == 200
    db.refresh(sos_incident)
    assert sos_incident.live_tracking_active is False
    # The case itself stays open -- stopping sharing is not the same as
    # police closing the incident.
    assert sos_incident.status != "resolved"


def test_admin_can_stop_tracking_too(client, admin_headers, sos_incident):
    r = client.post(f"/api/incidents/{sos_incident.id}/stop-tracking", headers=admin_headers)
    assert r.status_code == 200
