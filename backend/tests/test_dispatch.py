"""Ranked dispatch: rank_units() ordering/filtering, and the dispatch-candidates
endpoint. Also pins that the trigger_sos() refactor onto dispatch.rank_units()
did not change its existing behavior/return shape."""
import pytest

from app.models.incident import Incident
from app.services.dispatch import rank_units
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


def test_rank_units_orders_by_distance(db):
    far = make_unit(db, name="Far", lat=27.0, lng=92.5)
    near = make_unit(db, name="Near", lat=26.1450, lng=91.7365)
    mid = make_unit(db, name="Mid", lat=26.30, lng=91.90)

    ranked = rank_units(db, 26.1445, 91.7362)

    assert [r["unit_id"] for r in ranked] == [near.id, mid.id, far.id]
    assert ranked[0]["distance_km"] < ranked[1]["distance_km"] < ranked[2]["distance_km"]
    assert ranked[0]["eta_min"] > 0


def test_rank_units_respects_needed_types(db):
    make_unit(db, name="Cop", lat=26.1450, lng=91.7365, unit_type="police")
    amb = make_unit(db, name="Amb", lat=26.20, lng=91.80, unit_type="ambulance")

    ranked = rank_units(db, 26.1445, 91.7362, needed_types=["ambulance"])

    assert len(ranked) == 1
    assert ranked[0]["unit_id"] == amb.id
    assert ranked[0]["unit_type"] == "ambulance"


def test_rank_units_excludes_unavailable(db):
    make_unit(db, name="Busy", lat=26.1450, lng=91.7365, available=False)
    free = make_unit(db, name="Free", lat=26.20, lng=91.80, available=True)

    ranked = rank_units(db, 26.1445, 91.7362)

    assert [r["unit_id"] for r in ranked] == [free.id]


def test_rank_units_empty_when_nothing_available(db):
    assert rank_units(db, 26.1445, 91.7362) == []


# ---------------------------------------------------------------- endpoint
@pytest.fixture
def incident(db):
    make_unit(db, name="Alpha", lat=26.1450, lng=91.7365)
    make_unit(db, name="Bravo", lat=26.20, lng=91.80)
    t = make_tourist(db, name="Victim")
    result = trigger_sos(db, t, 26.1445, 91.7362, "help")
    return db.get(Incident, result["incident_id"])


def test_dispatch_candidates_returns_ranked_list(client, admin_headers, incident):
    r = client.get(f"/api/incidents/{incident.id}/dispatch-candidates", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["distance_km"] <= body[1]["distance_km"]


def test_dispatch_candidates_visible_to_responder(client, responder_headers, incident):
    r = client.get(f"/api/incidents/{incident.id}/dispatch-candidates",
                   headers=responder_headers)
    assert r.status_code == 200


def test_dispatch_candidates_forbidden_for_tourist(client, tourist_headers, incident):
    r = client.get(f"/api/incidents/{incident.id}/dispatch-candidates",
                   headers=tourist_headers)
    assert r.status_code == 403


def test_dispatch_candidates_unknown_incident_404(client, admin_headers):
    assert client.get("/api/incidents/9999/dispatch-candidates",
                      headers=admin_headers).status_code == 404


# --------------------------------------------------- trigger_sos regression
def test_trigger_sos_return_shape_unchanged_after_dispatch_refactor(db):
    """trigger_sos() now sources its top pick from dispatch.rank_units()
    internally, but its own behavior/return contract must be identical."""
    make_unit(db, name="Far Unit", lat=27.0, lng=92.5)
    near = make_unit(db, name="Near Unit", lat=26.1450, lng=91.7365)
    t = make_tourist(db)

    result = trigger_sos(db, t, 26.1445, 91.7362, "Help")

    assert set(result.keys()) == {
        "incident_id", "nearest_unit", "notified_contacts",
        # Added for SOS live location sharing (services/emergency_location.py).
        "silent", "status", "live_tracking_active", "station_id", "station_name",
    }
    assert result["nearest_unit"]["name"] == "Near Unit"
    assert set(result["nearest_unit"].keys()) == {
        "name", "station", "phone", "lat", "lng", "distance_km",
    }
    inc = db.get(Incident, result["incident_id"])
    assert inc.assigned_unit_id == near.id
    assert inc.status == "dispatched"
    assert inc.escalation_deadline is not None
