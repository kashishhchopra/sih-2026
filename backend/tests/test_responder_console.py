"""Responder console: /incidents/mine scoping, role guards, and admin access
to the analogous admin views remaining unaffected."""
import pytest

from app.models.incident import Incident
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


@pytest.fixture
def mine_incident(db, responder_unit):
    """An incident dispatched to the responder's own unit."""
    make_unit(db, name="Other Unit", lat=40.0, lng=40.0)  # far away, not picked
    t = make_tourist(db, name="Victim")
    result = trigger_sos(db, t, responder_unit.lat, responder_unit.lng, "help")
    inc = db.get(Incident, result["incident_id"])
    assert inc.assigned_unit_id == responder_unit.id
    return inc


@pytest.fixture
def other_incident(db):
    """An incident dispatched to a different (non-responder) unit."""
    make_unit(db, name="Someone Else's Unit", lat=10.0, lng=10.0)
    t = make_tourist(db, name="Other Victim")
    result = trigger_sos(db, t, 10.0, 10.0, "help")
    return db.get(Incident, result["incident_id"])


def test_incidents_mine_returns_only_my_units_incidents(
    client, responder_headers, mine_incident, other_incident
):
    r = client.get("/api/incidents/mine", headers=responder_headers)
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()]
    assert mine_incident.id in ids
    assert other_incident.id not in ids


def test_incidents_mine_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/incidents/mine", headers=tourist_headers)
    assert r.status_code == 403


def test_incidents_mine_admin_can_access(client, admin_headers):
    r = client.get("/api/incidents/mine", headers=admin_headers)
    assert r.status_code == 200


def test_incidents_mine_paginated_with_total_count_header(
    client, responder_headers, mine_incident
):
    r = client.get("/api/incidents/mine?limit=1", headers=responder_headers)
    assert r.status_code == 200
    assert "X-Total-Count" in r.headers


def test_admin_incidents_list_unaffected_by_responder_role(
    client, admin_headers, mine_incident, other_incident
):
    r = client.get("/api/incidents", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_responder_can_resolve_their_own_incident(client, responder_headers, mine_incident):
    r = client.patch(f"/api/incidents/{mine_incident.id}",
                     json={"status": "resolved", "note": "handled"},
                     headers=responder_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"


def test_responder_cannot_resolve_someone_elses_incident(
    client, responder_headers, other_incident
):
    r = client.patch(f"/api/incidents/{other_incident.id}",
                     json={"status": "resolved", "note": "handled"},
                     headers=responder_headers)
    assert r.status_code == 403


def test_responder_can_acknowledge_their_own_incident(client, responder_headers, mine_incident):
    r = client.post(f"/api/incidents/{mine_incident.id}/acknowledge", headers=responder_headers)
    assert r.status_code == 200
