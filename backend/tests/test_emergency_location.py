"""SOS live location sharing: services/emergency_location.py."""
from datetime import timedelta

import pytest

from app.core.time import utc_now
from app.models.emergency_location import EmergencyLocationPing
from app.services import emergency_location as svc
from app.services.monitoring import trigger_sos
from tests.conftest import make_tourist, make_unit


def _sos_incident(db):
    t = make_tourist(db)
    result = trigger_sos(db, t, 26.1445, 91.7362, "Help")
    from app.models.incident import Incident
    return db.get(Incident, result["incident_id"])


def test_sos_starts_live_tracking_immediately(db):
    inc = _sos_incident(db)
    assert inc.live_tracking_active is True


def test_record_location_updates_incident_position(db):
    inc = _sos_incident(db)
    svc.record_location(db, inc, 26.15, 91.74, accuracy_m=8, speed_kmh=3.2, heading_deg=92)
    assert inc.lat == 26.15
    assert inc.lng == 91.74


def test_record_location_rejects_updates_once_tracking_is_stopped(db):
    inc = _sos_incident(db)
    svc.stop_tracking(db, inc, "tourist stopped sharing")
    with pytest.raises(svc.EmergencyLocationError):
        svc.record_location(db, inc, 26.15, 91.74, None, None, None)


def test_record_location_rejects_updates_for_a_resolved_incident(db):
    inc = _sos_incident(db)
    inc.status = "resolved"
    with pytest.raises(svc.EmergencyLocationError):
        svc.record_location(db, inc, 26.15, 91.74, None, None, None)


def test_trail_is_bounded_not_unlimited(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "EMERGENCY_LOCATION_TRAIL_MAX_POINTS", 5)
    inc = _sos_incident(db)
    for i in range(12):
        svc.record_location(db, inc, 26.1445 + i * 0.0001, 91.7362, None, None, None)
    count = db.query(EmergencyLocationPing).filter_by(incident_id=inc.id).count()
    assert count == 5


def test_trail_keeps_the_most_recent_points(db, monkeypatch):
    monkeypatch.setattr(svc.settings, "EMERGENCY_LOCATION_TRAIL_MAX_POINTS", 3)
    inc = _sos_incident(db)
    for i in range(5):
        svc.record_location(db, inc, 26.0 + i, 91.0, None, None, None)
    track = svc.build_track(db, inc)
    lats = [p.lat for p in track["trail"]]
    assert lats == [28.0, 29.0, 30.0]  # oldest -> newest of the last 3


def test_implausible_jump_is_flagged_not_rejected(db):
    inc = _sos_incident(db)
    svc.record_location(db, inc, 26.1445, 91.7362, None, None, None)
    # "Teleporting" ~1100km in the next instant -- physically implausible.
    ping = svc.record_location(db, inc, 35.0, 91.7362, None, None, None)
    assert ping.anomaly_flag is True
    # Never auto-escalates anything -- the incident is untouched otherwise.
    assert inc.status != "resolved"


def test_normal_movement_is_not_flagged(db):
    inc = _sos_incident(db)
    svc.record_location(db, inc, 26.1445, 91.7362, None, None, None)
    ping = svc.record_location(db, inc, 26.1450, 91.7365, None, None, None)
    assert ping.anomaly_flag is False


def test_location_status_live_stale_offline(monkeypatch):
    monkeypatch.setattr(svc.settings, "EMERGENCY_LOCATION_LIVE_SECONDS", 15)
    monkeypatch.setattr(svc.settings, "EMERGENCY_LOCATION_STALE_SECONDS", 45)
    now = utc_now()
    assert svc.location_status(now - timedelta(seconds=5))[0] == "live"
    assert svc.location_status(now - timedelta(seconds=30))[0] == "stale"
    assert svc.location_status(now - timedelta(seconds=120))[0] == "offline"
    assert svc.location_status(None)[0] == "no_data"


def test_stop_tracking_is_idempotent(db):
    inc = _sos_incident(db)
    svc.stop_tracking(db, inc, "tourist stopped sharing")
    assert inc.live_tracking_active is False
    svc.stop_tracking(db, inc, "tourist stopped sharing")  # no error, no-op
    assert inc.live_tracking_active is False


def test_list_active_emergencies_only_includes_live_open_incidents(db):
    live_inc = _sos_incident(db)
    svc.record_location(db, live_inc, 26.15, 91.74, None, None, None)

    stopped_inc = _sos_incident(db)
    svc.stop_tracking(db, stopped_inc, "tourist stopped sharing")
    db.flush()  # what the real API layer always does before any later read

    active = svc.list_active_emergencies(db)
    ids = [a["incident_id"] for a in active]
    assert live_inc.id in ids
    assert stopped_inc.id not in ids


def test_build_track_reports_station_and_status(db):
    make_unit(db)
    inc = _sos_incident(db)
    svc.record_location(db, inc, 26.15, 91.74, accuracy_m=6, speed_kmh=2, heading_deg=10)
    track = svc.build_track(db, inc)
    assert track["location_status"] == "live"
    assert track["latest"].lat == 26.15
    assert track["tourist_name"]
    assert track["digital_id"]


def test_build_track_includes_full_tourist_and_case_detail(db):
    """A station a case is transferred to must have everything in this one
    call -- see services/police_network.py:send_case."""
    t = make_tourist(db, name="Priya Sharma")
    t.phone = "9876543210"
    t.nationality = "Indian"
    t.hotel = "ABC Residency"
    result = trigger_sos(db, t, 26.1445, 91.7362, "Help")
    from app.models.incident import Incident
    inc = db.get(Incident, result["incident_id"])

    track = svc.build_track(db, inc)
    assert track["tourist_phone"] == "9876543210"
    assert track["tourist_nationality"] == "Indian"
    assert track["hotel"] == "ABC Residency"
    assert track["safety_score"] is not None
    assert isinstance(track["emergency_contacts"], list)
    assert track["description"]
    assert track["detected_at"] is not None
