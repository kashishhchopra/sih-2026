"""Smart SOS escalation: tick_escalations() stage advancement, notification
dispatch, and the /acknowledge endpoint that stops the clock."""
from datetime import timedelta

import pytest

from app.core.time import utc_now
from app.models.incident import Incident, IncidentEvent
from app.services.escalation import tick_escalations
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


@pytest.fixture
def sos_incident(db):
    make_unit(db)
    t = make_tourist(db, name="Victim")
    result = trigger_sos(db, t, 26.1445, 91.7362, "help")
    return db.get(Incident, result["incident_id"])


def _expire(inc):
    inc.escalation_deadline = utc_now() - timedelta(seconds=1)


def test_tick_advances_control_room_to_emergency_contact(db, sos_incident, monkeypatch):
    from app.services import notifications

    sent = []
    monkeypatch.setattr(
        notifications, "get_channel",
        lambda: type("C", (), {"send": staticmethod(
            lambda to, subject, body: sent.append(to)
        )})(),
    )

    assert sos_incident.escalation_stage == "control_room"
    _expire(sos_incident)
    db.commit()

    advanced = tick_escalations(db)

    assert sos_incident.id in advanced
    db.refresh(sos_incident)
    assert sos_incident.escalation_stage == "emergency_contact"
    assert sos_incident.escalation_deadline is not None
    assert sent, "emergency contacts must be notified on this transition"
    events = db.query(IncidentEvent).filter_by(incident_id=sos_incident.id).all()
    assert any("emergency_contact" in e.status for e in events)


def test_tick_advances_emergency_contact_to_responder_dispatch(db, sos_incident):
    sos_incident.escalation_stage = "emergency_contact"
    sos_incident.assigned_unit_id = None
    _expire(sos_incident)
    db.commit()

    another = make_unit(db, name="Backup Unit", lat=26.20, lng=91.80)

    tick_escalations(db)

    db.refresh(sos_incident)
    assert sos_incident.escalation_stage == "responder_dispatch"
    assert sos_incident.assigned_unit_id is not None
    assert sos_incident.assigned_unit_id in {another.id, sos_incident.assigned_unit_id}


def test_tick_leaves_future_deadlines_untouched(db, sos_incident):
    sos_incident.escalation_deadline = utc_now() + timedelta(hours=1)
    db.commit()

    advanced = tick_escalations(db)

    assert advanced == []
    db.refresh(sos_incident)
    assert sos_incident.escalation_stage == "control_room"


def test_tick_ignores_already_acknowledged_incidents(db, sos_incident):
    sos_incident.escalation_stage = "acknowledged"
    _expire(sos_incident)
    db.commit()

    advanced = tick_escalations(db)

    assert advanced == []
    db.refresh(sos_incident)
    assert sos_incident.escalation_stage == "acknowledged"


def test_tick_ignores_resolved_incidents(db, sos_incident):
    sos_incident.status = "resolved"
    _expire(sos_incident)
    db.commit()

    advanced = tick_escalations(db)

    assert advanced == []


def test_acknowledge_endpoint_stops_escalation(client, admin_headers, db, sos_incident):
    r = client.post(f"/api/incidents/{sos_incident.id}/acknowledge", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["escalation_stage"] == "acknowledged"
    assert body["escalation_deadline"] is None

    _expire(sos_incident)
    db.commit()
    advanced = tick_escalations(db)
    assert advanced == []


def test_acknowledge_forbidden_for_tourist(client, tourist_headers, sos_incident):
    r = client.post(f"/api/incidents/{sos_incident.id}/acknowledge", headers=tourist_headers)
    assert r.status_code == 403


def test_acknowledge_unknown_incident_404(client, admin_headers):
    assert client.post("/api/incidents/9999/acknowledge",
                       headers=admin_headers).status_code == 404
