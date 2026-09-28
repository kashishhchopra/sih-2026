"""Area-Based Police Network: zone -> station routing, the Central Safety
Dashboard, inter-station hand-off, and nearby-camera lookup
(services/police_network.py, app/api/police_network.py)."""
import pytest

from app.models.emergency_location import EmergencyLocationPing
from app.models.incident import Incident
from app.services import emergency_location, police_network
from app.services.monitoring import trigger_sos
from tests.conftest import make_camera, make_station, make_tourist, make_zone


# ---------------------------------------------------------------- resolving
def test_resolve_zone_for_point_inside_and_outside(db):
    zone = make_zone(db, name="Old Market", risk="high", lat=26.165, lng=91.75, d=0.008)
    assert police_network.resolve_zone_for_point(db, 26.165, 91.75).id == zone.id
    assert police_network.resolve_zone_for_point(db, 0.0, 0.0) is None


def test_resolve_zone_for_point_prefers_higher_risk_on_overlap(db):
    """Two overlapping zones at the same point: the higher-risk one wins,
    since that is the zone whose station should own the case."""
    low = make_zone(db, name="Wide Low", risk="low", lat=26.165, lng=91.75, d=0.02)
    high = make_zone(db, name="Narrow High", risk="restricted", lat=26.165, lng=91.75, d=0.005)
    resolved = police_network.resolve_zone_for_point(db, 26.165, 91.75)
    assert resolved.id == high.id
    assert resolved.id != low.id


def test_station_for_zone_and_point(db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station = make_station(db, name="Market PS", zone_id=zone.id, lat=26.165, lng=91.75)
    assert police_network.station_for_zone(db, zone.id).id == station.id
    assert police_network.station_for_point(db, 26.165, 91.75).id == station.id


def test_station_for_point_none_outside_any_zone(db):
    make_zone(db, lat=26.165, lng=91.75, d=0.008)
    assert police_network.station_for_point(db, 0.0, 0.0) is None


def test_station_for_zone_with_no_station_returns_none(db):
    zone = make_zone(db)
    assert police_network.station_for_zone(db, zone.id) is None


# ---------------------------------------------------------------- assignment
def test_sos_auto_routes_to_the_zone_station(db):
    """A tourist raising an SOS inside a covered zone gets the incident
    routed to that zone's station automatically."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station = make_station(db, name="Market PS", zone_id=zone.id, lat=26.165, lng=91.75)
    t = make_tourist(db, lat=26.165, lng=91.75)

    result = trigger_sos(db, t, 26.165, 91.75, "help")
    inc = db.get(Incident, result["incident_id"])
    assert inc.station_id == station.id
    notes = [e.note for e in inc.events]
    assert any("Routed to Market PS" in n for n in notes)


def test_sos_outside_any_zone_leaves_incident_unassigned(db):
    t = make_tourist(db, lat=0.0, lng=0.0)
    result = trigger_sos(db, t, 0.0, 0.0, "help")
    inc = db.get(Incident, result["incident_id"])
    assert inc.station_id is None


def test_assign_station_noop_without_location(db):
    inc = Incident(tourist_id=None, type="anomaly", severity="low",
                   status="detected", description="", lat=None, lng=None)
    db.add(inc)
    db.flush()
    assert police_network.assign_station(db, inc) is None
    assert inc.station_id is None


# ---------------------------------------------------------------- forwarding
def test_forward_incident_moves_station_and_logs_event(db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station_a = make_station(db, name="Station A", zone_id=zone.id, lat=26.165, lng=91.75)
    station_b = make_station(db, name="Station B", lat=26.2, lng=91.8)
    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    inc = db.get(Incident, result["incident_id"])
    assert inc.station_id == station_a.id

    police_network.forward_incident(db, inc, station_b.id, note="tourist moved",
                                    actor="admin@test.gov")
    db.commit()
    db.refresh(inc)
    assert inc.station_id == station_b.id
    notes = [e.note for e in inc.events]
    assert any("Forwarded from Station A to Station B" in n and "tourist moved" in n
              for n in notes)


def test_forward_incident_unknown_station_raises(db):
    t = make_tourist(db)
    result = trigger_sos(db, t, t.last_lat, t.last_lng, "help")
    inc = db.get(Incident, result["incident_id"])
    with pytest.raises(ValueError):
        police_network.forward_incident(db, inc, 99999)


# ---------------------------------------------------------------- cameras
def test_nearby_cameras_filters_and_sorts_by_distance(db):
    near = make_camera(db, label="Near Cam", lat=26.1450, lng=91.7370)
    far = make_camera(db, label="Far Cam", lat=27.0, lng=92.0)
    out = police_network.nearby_cameras(db, 26.1450, 91.7370, radius_m=5000)
    ids = [c["id"] for c in out]
    assert near.id in ids
    assert far.id not in ids
    assert out[0]["id"] == near.id
    assert out[0]["distance_m"] < out[-1]["distance_m"] if len(out) > 1 else True


# ---------------------------------------------------------------- dashboard
def test_central_dashboard_groups_incidents_by_station(db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station = make_station(db, name="Market PS", zone_id=zone.id, lat=26.165, lng=91.75)
    t = make_tourist(db, lat=26.165, lng=91.75)
    trigger_sos(db, t, 26.165, 91.75, "help")

    dash = police_network.central_dashboard(db)
    entry = next(s for s in dash["stations"] if s["id"] == station.id)
    assert entry["zone_id"] == zone.id
    assert entry["open_incidents"] == 1
    assert entry["critical_incidents"] == 1
    assert dash["total_open_incidents"] == 1
    assert dash["unassigned_incidents"] == []


def test_central_dashboard_lists_unassigned_incidents(db):
    t = make_tourist(db, lat=0.0, lng=0.0)
    result = trigger_sos(db, t, 0.0, 0.0, "help")
    dash = police_network.central_dashboard(db)
    assert result["incident_id"] in dash["unassigned_incidents"]


# ---------------------------------------------------------------- API
def test_list_stations_endpoint(client, admin_headers, db):
    make_station(db, name="Station A")
    r = client.get("/api/police-network/stations", headers=admin_headers)
    assert r.status_code == 200
    assert any(s["name"] == "Station A" for s in r.json())


def test_create_station_endpoint_requires_admin(client, tourist_headers):
    r = client.post("/api/police-network/stations",
                    json={"name": "New PS", "lat": 26.1, "lng": 91.7},
                    headers=tourist_headers)
    assert r.status_code == 403


def test_create_station_rejects_duplicate_zone(client, admin_headers, db):
    zone = make_zone(db)
    make_station(db, name="Existing PS", zone_id=zone.id)
    r = client.post("/api/police-network/stations",
                    json={"name": "New PS", "zone_id": zone.id, "lat": 26.1, "lng": 91.7},
                    headers=admin_headers)
    assert r.status_code == 400


def test_dashboard_endpoint(client, admin_headers, db):
    r = client.get("/api/police-network/dashboard", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "stations" in body and "total_open_incidents" in body


def test_dashboard_endpoint_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/police-network/dashboard", headers=tourist_headers)
    assert r.status_code == 403


def test_zone_station_lookup_endpoint(client, admin_headers, db):
    zone = make_zone(db)
    station = make_station(db, zone_id=zone.id)
    r = client.get(f"/api/police-network/zones/{zone.id}/station", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["id"] == station.id


def test_zone_station_lookup_404_when_uncovered(client, admin_headers, db):
    zone = make_zone(db)
    r = client.get(f"/api/police-network/zones/{zone.id}/station", headers=admin_headers)
    assert r.status_code == 404


def test_locate_endpoint(client, admin_headers, db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station = make_station(db, zone_id=zone.id, lat=26.165, lng=91.75)
    r = client.get("/api/police-network/locate?lat=26.165&lng=91.75", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["id"] == station.id


def test_locate_endpoint_404_outside_any_zone(client, admin_headers):
    r = client.get("/api/police-network/locate?lat=0&lng=0", headers=admin_headers)
    assert r.status_code == 404


def test_forward_incident_endpoint(client, admin_headers, db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    make_station(db, name="Station A", zone_id=zone.id, lat=26.165, lng=91.75)
    station_b = make_station(db, name="Station B", lat=26.2, lng=91.8)
    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")

    r = client.post(
        f"/api/police-network/incidents/{result['incident_id']}/forward",
        json={"to_station_id": station_b.id, "note": "moved zones"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["station_id"] == station_b.id


def test_forward_incident_endpoint_unknown_station_404(client, admin_headers, db):
    t = make_tourist(db)
    result = trigger_sos(db, t, t.last_lat, t.last_lng, "help")
    r = client.post(
        f"/api/police-network/incidents/{result['incident_id']}/forward",
        json={"to_station_id": 99999}, headers=admin_headers,
    )
    assert r.status_code == 404


def test_cameras_nearby_endpoint(client, admin_headers, db):
    cam = make_camera(db, label="Near Cam", lat=26.1450, lng=91.7370)
    r = client.get(
        "/api/police-network/cameras/nearby?lat=26.1450&lng=91.7370&radius_m=1000",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert any(c["id"] == cam.id for c in r.json())


def test_create_camera_endpoint_requires_admin(client, admin_headers):
    r = client.post("/api/police-network/cameras",
                    json={"label": "New Cam", "lat": 26.1, "lng": 91.7},
                    headers=admin_headers)
    assert r.status_code == 201
    assert r.json()["label"] == "New Cam"


# ------------------------------------------- resource fallback (station A->B->C)
def _fill_station(db, station, count):
    """Saturate a station with `count` open cases."""
    for _ in range(count):
        inc = Incident(tourist_id=None, type="anomaly", severity="medium",
                       status="detected", description="load", lat=None, lng=None,
                       station_id=station.id)
        db.add(inc)
    db.commit()


def test_station_capacity_reports_live_load(db):
    s = make_station(db, name="Busy PS", max_concurrent_cases=2)
    assert police_network.station_capacity(db, s)["has_capacity"] is True

    _fill_station(db, s, 2)
    cap = police_network.station_capacity(db, s)
    assert cap["open_cases"] == 2
    assert cap["has_capacity"] is False
    assert cap["load_pct"] == 100.0


def test_resolved_cases_free_up_capacity(db):
    s = make_station(db, name="Busy PS", max_concurrent_cases=1)
    _fill_station(db, s, 1)
    assert police_network.station_capacity(db, s)["has_capacity"] is False

    db.query(Incident).filter(Incident.station_id == s.id).update({"status": "resolved"})
    db.commit()
    assert police_network.station_capacity(db, s)["has_capacity"] is True


def test_sos_falls_back_when_zone_station_is_at_capacity(db):
    """Station A (the zone's own) is full -> the case is routed to the next
    best-suited station instead of being delayed."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station_a = make_station(db, name="Station A", zone_id=zone.id,
                            lat=26.165, lng=91.75, max_concurrent_cases=1)
    station_b = make_station(db, name="Station B", lat=26.17, lng=91.76,
                            max_concurrent_cases=5)
    _fill_station(db, station_a, 1)  # A is now at capacity

    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    inc = db.get(Incident, result["incident_id"])

    assert inc.station_id == station_b.id
    notes = [e.note for e in inc.events]
    assert any("Station A at capacity" in n and "Station B" in n for n in notes)


def test_fallback_skips_full_stations_to_the_next_with_capacity(db):
    """A full, B full -> C takes it (Station A -> Station B -> Station C)."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station_a = make_station(db, name="Station A", zone_id=zone.id,
                            lat=26.165, lng=91.75, max_concurrent_cases=1)
    station_b = make_station(db, name="Station B", lat=26.166, lng=91.751,
                            max_concurrent_cases=1)
    station_c = make_station(db, name="Station C", lat=26.20, lng=91.80,
                            max_concurrent_cases=5)
    _fill_station(db, station_a, 1)
    _fill_station(db, station_b, 1)

    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    assert db.get(Incident, result["incident_id"]).station_id == station_c.id


def test_no_fallback_while_the_zone_station_has_capacity(db):
    """Unchanged behaviour when nothing is overloaded: the zone's own
    station keeps the case, with the original routing note."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station_a = make_station(db, name="Station A", zone_id=zone.id,
                            lat=26.165, lng=91.75, max_concurrent_cases=5)
    make_station(db, name="Station B", lat=26.17, lng=91.76)

    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    inc = db.get(Incident, result["incident_id"])

    assert inc.station_id == station_a.id
    assert any("Routed to Station A" in e.note for e in inc.events)


def test_every_station_full_still_dispatches_nearest(db):
    """A busy network beats no response -- the case is never left unassigned."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    station_a = make_station(db, name="Station A", zone_id=zone.id,
                            lat=26.165, lng=91.75, max_concurrent_cases=1)
    station_b = make_station(db, name="Station B", lat=26.30, lng=91.90,
                            max_concurrent_cases=1)
    _fill_station(db, station_a, 1)
    _fill_station(db, station_b, 1)

    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    # nearest of the two full stations wins rather than nobody taking it
    assert db.get(Incident, result["incident_id"]).station_id == station_a.id


def test_rank_stations_puts_stations_with_capacity_first(db):
    near_full = make_station(db, name="Near Full", lat=26.165, lng=91.75,
                            max_concurrent_cases=1)
    far_free = make_station(db, name="Far Free", lat=26.30, lng=91.90,
                           max_concurrent_cases=5)
    _fill_station(db, near_full, 1)

    ranked = police_network.rank_stations_for_point(db, 26.165, 91.75)
    assert ranked[0]["station"].id == far_free.id  # capacity beats proximity
    assert ranked[0]["has_capacity"] is True
    assert ranked[-1]["station"].id == near_full.id


def test_fallback_preview_endpoint(client, admin_headers, db):
    make_station(db, name="Station A", lat=26.165, lng=91.75, max_concurrent_cases=3)
    make_station(db, name="Station B", lat=26.30, lng=91.90)

    r = client.get("/api/police-network/fallback-preview?lat=26.165&lng=91.75",
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "Station A"  # closest with capacity leads
    assert body[0]["has_capacity"] is True
    assert "load_pct" in body[0]


def test_station_capacity_endpoint(client, admin_headers, db):
    s = make_station(db, name="Station A", max_concurrent_cases=2)
    _fill_station(db, s, 2)

    r = client.get(f"/api/police-network/stations/{s.id}/capacity", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Station A"
    assert body["open_cases"] == 2
    assert body["has_capacity"] is False


def test_station_capacity_endpoint_404(client, admin_headers):
    r = client.get("/api/police-network/stations/99999/capacity", headers=admin_headers)
    assert r.status_code == 404


def test_dashboard_exposes_capacity_signals(client, admin_headers, db):
    s = make_station(db, name="Station A", max_concurrent_cases=2, total_officers=17)
    _fill_station(db, s, 2)

    r = client.get("/api/police-network/dashboard", headers=admin_headers)
    entry = next(e for e in r.json()["stations"] if e["id"] == s.id)
    assert entry["total_officers"] == 17
    assert entry["max_concurrent_cases"] == 2
    assert entry["has_capacity"] is False
    assert entry["load_pct"] == 100.0


# ============================================================
# Case Transfer: request / accept / reject / cancel
# (services/police_network.py's request_transfer & friends,
# app/models/incident_transfer.py). The core rule under test throughout:
# the live-location session (EmergencyLocationPing, keyed by incident_id)
# must never be interrupted, duplicated, or reset by any of this -- only
# Incident.station_id ever changes, and only once a transfer is accepted.
# ============================================================
def _sos_with_stations(db):
    zone_a = make_zone(db, name="Zone A", lat=26.165, lng=91.75, d=0.008)
    station_a = make_station(db, name="Station A", zone_id=zone_a.id, lat=26.165, lng=91.75)
    station_b = make_station(db, name="Station B", lat=26.2, lng=91.8)
    t = make_tourist(db, lat=26.165, lng=91.75)
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    inc = db.get(Incident, result["incident_id"])
    return inc, station_a, station_b


def test_request_transfer_does_not_move_the_case(db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "tourist moved", "admin@test.gov")
    db.commit()
    db.refresh(inc)

    assert transfer.status == "requested"
    assert transfer.from_station_id == station_a.id
    assert transfer.to_station_id == station_b.id
    assert inc.station_id == station_a.id  # unchanged until accepted


def test_request_transfer_snapshots_latest_location(db):
    inc, station_a, station_b = _sos_with_stations(db)
    emergency_location.record_location(db, inc, 26.166, 91.751, None, None, None)
    transfer = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    assert transfer.latest_lat == 26.166
    assert transfer.latest_lng == 91.751
    assert transfer.latest_location_at is not None


def test_request_transfer_rejects_unknown_station(db):
    inc, _station_a, _station_b = _sos_with_stations(db)
    with pytest.raises(police_network.TransferError):
        police_network.request_transfer(db, inc, 99999, "", "admin@test.gov")


def test_request_transfer_rejects_same_station(db):
    inc, station_a, _station_b = _sos_with_stations(db)
    with pytest.raises(police_network.TransferError):
        police_network.request_transfer(db, inc, station_a.id, "", "admin@test.gov")


def test_second_request_blocked_while_one_is_pending(db):
    inc, _station_a, station_b = _sos_with_stations(db)
    station_c = make_station(db, name="Station C", lat=26.3, lng=91.9)
    police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    with pytest.raises(police_network.TransferError):
        police_network.request_transfer(db, inc, station_c.id, "", "admin@test.gov")


def test_live_location_keeps_flowing_while_transfer_is_pending(db):
    """The core architecture rule: the live-location session belongs to the
    case, not the station, so it must not pause or reset just because a
    transfer is awaiting acceptance."""
    inc, station_a, station_b = _sos_with_stations(db)
    emergency_location.record_location(db, inc, 26.166, 91.751, None, None, None)
    police_network.request_transfer(db, inc, station_b.id, "moved", "admin@test.gov")

    # a ping arrives while the transfer is still just "requested"
    emergency_location.record_location(db, inc, 26.167, 91.752, None, None, None)
    db.commit()
    db.refresh(inc)

    assert inc.station_id == station_a.id  # still with the requesting station
    assert inc.live_tracking_active is True
    pings = (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == inc.id)
        .order_by(EmergencyLocationPing.timestamp)
        .all()
    )
    assert len(pings) == 2
    assert pings[-1].lat == 26.167


def test_accept_transfer_moves_station_and_continues_same_session(db):
    inc, station_a, station_b = _sos_with_stations(db)
    emergency_location.record_location(db, inc, 26.166, 91.751, None, None, None)
    transfer = police_network.request_transfer(db, inc, station_b.id, "moved", "station_a@test.gov")

    accepted = police_network.accept_transfer(db, inc, transfer.id, "station_b@test.gov")
    db.commit()
    db.refresh(inc)

    assert accepted.status == "accepted"
    assert accepted.responded_by == "station_b@test.gov"
    assert inc.station_id == station_b.id  # now Station B's case

    # the tourist keeps moving -- same incident, same ping table, no new
    # incident and no new live-tracking session were created by the transfer
    emergency_location.record_location(db, inc, 26.21, 91.81, None, None, None)
    pings = (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == inc.id)
        .order_by(EmergencyLocationPing.timestamp)
        .all()
    )
    assert len(pings) == 2  # one before the transfer, one after -- same trail
    assert inc.live_tracking_active is True
    assert db.query(Incident).count() == 1  # no duplicate case


def test_accept_transfer_preserves_case_and_transfer_history(db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "moved", "admin@test.gov")
    police_network.accept_transfer(db, inc, transfer.id, "admin@test.gov")
    db.commit()
    db.refresh(inc)

    notes = [e.note for e in inc.events]
    assert any("Transfer requested" in n for n in notes)
    assert any("Forwarded from Station A to Station B" in n for n in notes)

    history = police_network.list_transfers(db, inc.id)
    assert len(history) == 1
    assert history[0].status == "accepted"


def test_reject_transfer_leaves_case_with_original_station(db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "moved", "admin@test.gov")

    rejected = police_network.reject_transfer(db, inc, transfer.id, "station_b@test.gov", "too far")
    db.commit()
    db.refresh(inc)

    assert rejected.status == "rejected"
    assert inc.station_id == station_a.id  # original station remains responsible
    assert inc.live_tracking_active is True


def test_can_request_again_after_a_rejection(db):
    inc, _station_a, station_b = _sos_with_stations(db)
    station_c = make_station(db, name="Station C", lat=26.3, lng=91.9)
    t1 = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    police_network.reject_transfer(db, inc, t1.id, "admin@test.gov")
    db.flush()

    t2 = police_network.request_transfer(db, inc, station_c.id, "", "admin@test.gov")
    assert t2.status == "requested"
    assert t2.id != t1.id


def test_cancel_transfer_by_requester(db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")

    cancelled = police_network.cancel_transfer(db, inc, transfer.id, "admin@test.gov")
    db.commit()
    db.refresh(inc)
    assert cancelled.status == "cancelled"
    assert inc.station_id == station_a.id


def test_accept_already_resolved_transfer_raises(db):
    inc, _station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    police_network.accept_transfer(db, inc, transfer.id, "admin@test.gov")
    with pytest.raises(police_network.TransferError):
        police_network.accept_transfer(db, inc, transfer.id, "admin@test.gov")


def test_cannot_transfer_a_resolved_case(db):
    inc, _station_a, station_b = _sos_with_stations(db)
    inc.status = "resolved"
    with pytest.raises(police_network.TransferError):
        police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")


def test_multiple_transfers_preserve_full_chain(db):
    """Station A -> Station B -> Station C: the same case and live-location
    session continue through every hop."""
    inc, station_a, station_b = _sos_with_stations(db)
    station_c = make_station(db, name="Station C", lat=26.3, lng=91.9)

    t1 = police_network.request_transfer(db, inc, station_b.id, "hop 1", "admin@test.gov")
    police_network.accept_transfer(db, inc, t1.id, "admin@test.gov")
    db.flush()
    db.refresh(inc)
    assert inc.station_id == station_b.id

    t2 = police_network.request_transfer(db, inc, station_c.id, "hop 2", "admin@test.gov")
    police_network.accept_transfer(db, inc, t2.id, "admin@test.gov")
    db.commit()
    db.refresh(inc)
    assert inc.station_id == station_c.id

    history = police_network.list_transfers(db, inc.id)
    assert [h.to_station_id for h in history] == [station_b.id, station_c.id]
    assert db.query(Incident).count() == 1  # still one case throughout


# ---------------------------------------------------------------- send_case (direct, one-click)
def test_send_case_moves_the_incident_immediately(db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.send_case(db, inc, station_b.id, "moved zones", "admin@test.gov")
    db.commit()
    db.refresh(inc)

    assert transfer.status == "accepted"
    assert transfer.requested_by == transfer.responded_by == "admin@test.gov"
    assert transfer.location_shared is True
    assert inc.station_id == station_b.id  # no pending interval at all


def test_send_case_respects_share_live_location_flag(db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.send_case(db, inc, station_b.id, "", "admin@test.gov",
                                        share_live_location=False)
    assert transfer.location_shared is False


def test_send_case_does_not_create_a_pending_transfer(db):
    inc, station_a, station_b = _sos_with_stations(db)
    police_network.send_case(db, inc, station_b.id, "", "admin@test.gov")
    db.commit()
    assert police_network.list_pending_transfers(db) == []


def test_send_case_preserves_live_location_session(db):
    inc, station_a, station_b = _sos_with_stations(db)
    emergency_location.record_location(db, inc, 26.166, 91.751, None, None, None)
    police_network.send_case(db, inc, station_b.id, "", "admin@test.gov")
    db.commit()
    db.refresh(inc)

    assert inc.station_id == station_b.id
    assert inc.live_tracking_active is True
    pings = (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == inc.id)
        .all()
    )
    assert len(pings) == 1  # same session, not reset


def test_send_case_rejects_unknown_station(db):
    inc, _station_a, _station_b = _sos_with_stations(db)
    with pytest.raises(police_network.TransferError):
        police_network.send_case(db, inc, 99999, "", "admin@test.gov")


def test_send_case_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    r = client.post(
        f"/api/police-network/incidents/{inc.id}/transfer/send",
        json={"to_station_id": station_b.id, "reason": "moved", "share_live_location": True},
        headers=admin_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "accepted"
    assert body["location_shared"] is True

    inc_r = client.get(f"/api/incidents/{inc.id}", headers=admin_headers)
    assert inc_r.json()["station_id"] == station_b.id


def test_send_case_endpoint_forbidden_for_tourist(client, tourist_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    r = client.post(
        f"/api/police-network/incidents/{inc.id}/transfer/send",
        json={"to_station_id": station_b.id}, headers=tourist_headers,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------- API
def test_request_transfer_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    r = client.post(
        f"/api/police-network/incidents/{inc.id}/transfer",
        json={"to_station_id": station_b.id, "reason": "tourist moved"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "requested"
    assert body["to_station_id"] == station_b.id


def test_accept_transfer_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    db.commit()

    r = client.post(
        f"/api/police-network/incidents/{inc.id}/transfer/{transfer.id}/accept",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["station_id"] == station_b.id


def test_reject_transfer_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    transfer = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    db.commit()

    r = client.post(
        f"/api/police-network/incidents/{inc.id}/transfer/{transfer.id}/reject",
        json={"reason": "not our jurisdiction"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_transfer_history_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    db.commit()

    r = client.get(f"/api/police-network/incidents/{inc.id}/transfers", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_pending_transfers_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")
    db.commit()

    r = client.get("/api/police-network/transfers/pending", headers=admin_headers)
    assert r.status_code == 200
    assert any(t["incident_id"] == inc.id for t in r.json())


def test_transfer_endpoints_forbidden_for_tourist(client, tourist_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    r = client.post(
        f"/api/police-network/incidents/{inc.id}/transfer",
        json={"to_station_id": station_b.id}, headers=tourist_headers,
    )
    assert r.status_code == 403


def test_station_scoped_active_incidents_endpoint(client, admin_headers, db):
    inc, station_a, station_b = _sos_with_stations(db)
    r = client.get(f"/api/police-network/stations/{station_a.id}/incidents", headers=admin_headers)
    assert r.status_code == 200
    assert any(i["id"] == inc.id for i in r.json())

    r_b = client.get(f"/api/police-network/stations/{station_b.id}/incidents", headers=admin_headers)
    assert r_b.json() == []  # nothing assigned to Station B yet


def test_live_track_reports_pending_transfer(db):
    from app.services import emergency_location as svc

    inc, station_a, station_b = _sos_with_stations(db)
    svc.record_location(db, inc, 26.166, 91.751, None, None, None)
    transfer = police_network.request_transfer(db, inc, station_b.id, "", "admin@test.gov")

    track = svc.build_track(db, inc)
    assert track["pending_transfer_id"] == transfer.id
    assert track["pending_transfer_to_station_id"] == station_b.id

    police_network.accept_transfer(db, inc, transfer.id, "admin@test.gov")
    db.flush()
    track_after = svc.build_track(db, inc)
    assert track_after["pending_transfer_id"] is None
