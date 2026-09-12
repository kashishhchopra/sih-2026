"""Incident Timeline & Replay (GET /incidents/{id}/timeline)."""
from app.models.alert import Alert
from app.models.incident import Incident
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


def test_timeline_includes_status_events(client, admin_headers, db):
    make_unit(db)
    t = make_tourist(db)
    result = trigger_sos(db, t, t.last_lat, t.last_lng, "help")
    inc_id = result["incident_id"]

    r = client.get(f"/api/incidents/{inc_id}/timeline", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["incident_id"] == inc_id
    kinds = [e["kind"] for e in body["events"]]
    assert "status" in kinds


def test_timeline_includes_related_alerts(client, admin_headers, db):
    make_unit(db)
    t = make_tourist(db)
    result = trigger_sos(db, t, t.last_lat, t.last_lng, "help")
    inc = db.get(Incident, result["incident_id"])
    db.add(Alert(tourist_id=t.id, type="anomaly", severity="high",
                 message="Speed spike", created_at=inc.detected_at))
    db.commit()

    r = client.get(f"/api/incidents/{inc.id}/timeline", headers=admin_headers)
    body = r.json()
    assert any(e["kind"] == "alert" and "Speed spike" in e["detail"] for e in body["events"])
    # events are chronologically ordered
    timestamps = [e["timestamp"] for e in body["events"]]
    assert timestamps == sorted(timestamps)


def test_timeline_unknown_incident_404(client, admin_headers):
    assert client.get("/api/incidents/9999/timeline", headers=admin_headers).status_code == 404


def test_timeline_visible_to_responder(client, responder_headers, db):
    make_unit(db)
    t = make_tourist(db)
    result = trigger_sos(db, t, t.last_lat, t.last_lng, "help")
    r = client.get(f"/api/incidents/{result['incident_id']}/timeline", headers=responder_headers)
    assert r.status_code == 200
