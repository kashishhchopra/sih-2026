"""Incident lifecycle, alert acknowledgement, and E-FIR generation."""
import pytest

from app.models.incident import Incident
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


@pytest.fixture
def incident(db):
    make_unit(db)
    t = make_tourist(db, name="Victim")
    result = trigger_sos(db, t, 26.1445, 91.7362, "help")
    return db.get(Incident, result["incident_id"])


def test_list_incidents(client, admin_headers, incident):
    r = client.get("/api/incidents", headers=admin_headers)
    assert r.status_code == 200 and len(r.json()) == 1


def test_list_incidents_includes_tourist_name_and_digital_id(client, admin_headers, incident, db):
    from app.models.tourist import Tourist

    tourist = db.get(Tourist, incident.tourist_id)
    body = client.get("/api/incidents", headers=admin_headers).json()[0]
    assert body["tourist_name"] == "Victim"
    assert body["tourist_digital_id"] == tourist.digital_id


def test_get_incident_includes_tourist_name_and_digital_id(client, admin_headers, incident):
    body = client.get(f"/api/incidents/{incident.id}", headers=admin_headers).json()
    assert body["tourist_name"] == "Victim"
    assert body["tourist_digital_id"]


def test_station_incidents_includes_tourist_name(client, admin_headers, db, incident):
    from tests.conftest import make_station

    station = make_station(db, name="Station A")
    incident.station_id = station.id
    db.commit()

    body = client.get(f"/api/police-network/stations/{station.id}/incidents",
                      headers=admin_headers).json()
    assert body[0]["tourist_name"] == "Victim"


def test_filter_incidents_by_status(client, admin_headers, incident):
    assert len(client.get("/api/incidents?status=dispatched",
                          headers=admin_headers).json()) == 1
    assert len(client.get("/api/incidents?status=resolved",
                          headers=admin_headers).json()) == 0


def test_advancing_status_stamps_the_timestamp(client, admin_headers, incident, db):
    r = client.patch(f"/api/incidents/{incident.id}",
                     json={"status": "resolved", "note": "closed"},
                     headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["response_time_seconds"] is not None


def test_resolving_sos_returns_tourist_to_active(client, admin_headers, incident, db):
    client.patch(f"/api/incidents/{incident.id}",
                 json={"status": "resolved", "note": "found safe"},
                 headers=admin_headers)
    from app.models.tourist import Tourist
    assert db.get(Tourist, incident.tourist_id).status == "active"


def test_status_transitions_are_recorded_as_events(client, admin_headers, incident):
    for status in ["acknowledged", "resolved"]:
        client.patch(f"/api/incidents/{incident.id}",
                     json={"status": status, "note": f"-> {status}"},
                     headers=admin_headers)
    events = client.get(f"/api/incidents/{incident.id}",
                        headers=admin_headers).json()["events"]
    assert {e["status"] for e in events} >= {"acknowledged", "resolved"}


@pytest.mark.parametrize("bad", ["detected", "closed", "", "RESOLVED"])
def test_invalid_status_rejected(client, admin_headers, incident, bad):
    r = client.patch(f"/api/incidents/{incident.id}",
                     json={"status": bad, "note": ""}, headers=admin_headers)
    assert r.status_code == 422


def test_unknown_incident_returns_404(client, admin_headers):
    assert client.get("/api/incidents/9999", headers=admin_headers).status_code == 404


def test_alerts_can_be_acknowledged(client, admin_headers, incident):
    alerts = client.get("/api/alerts", headers=admin_headers).json()
    assert alerts, "SOS should have produced an alert"
    aid = alerts[0]["id"]
    assert client.post(f"/api/alerts/{aid}/ack", headers=admin_headers).status_code == 200
    remaining = client.get("/api/alerts?only_active=true", headers=admin_headers).json()
    assert aid not in [a["id"] for a in remaining]


def test_mark_missing_opens_critical_incident_and_efir(client, admin_headers, db):
    t = make_tourist(db, name="Lost Person")
    r = client.post(f"/api/tourists/{t.id}/mark-missing", headers=admin_headers)
    assert r.status_code == 200

    body = r.json()
    assert body["status"] == "missing"
    assert body["efir"]["fir_number"].startswith("EFIR/")
    assert "Lost Person" in body["efir"]["narrative"]
    assert db.get(Incident, body["incident_id"]).severity == "critical"


def test_efir_contains_kyc_and_last_location(client, admin_headers, db):
    t = make_tourist(db, name="Lost Person", doc="XXXX-XXXX-4321")
    efir = client.post(f"/api/tourists/{t.id}/mark-missing",
                       headers=admin_headers).json()["efir"]
    assert efir["subject"]["document_number"] == "XXXX-XXXX-4321"
    assert efir["last_known_location"]["lat"] == t.last_lat
    assert efir["emergency_contacts"][0]["name"] == "Kin"


def test_police_units_visible_to_tourists(client, tourist_headers, db):
    make_unit(db)
    assert client.get("/api/police-units", headers=tourist_headers).status_code == 200
