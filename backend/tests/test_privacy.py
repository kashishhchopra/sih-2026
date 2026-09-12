"""Privacy & Consent Dashboard (services/privacy.py, /tourists/{id}/privacy)."""
from datetime import timedelta

from app.core.time import utc_now
from app.models.tourist import LocationPing, Tourist
from app.services.monitoring import process_ping
from app.services.privacy import tick_retention_purge
from tests.conftest import make_tourist


def test_privacy_report_shape(client, tourist_headers, tourist_user):
    tid = tourist_user.tourist_id
    r = client.get(f"/api/tourists/{tid}/privacy", headers=tourist_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["data_retention_days"] == 90
    assert body["tracking_enabled"] is True
    assert "auto_purge_at" in body


def test_update_privacy_settings(client, tourist_headers, tourist_user):
    tid = tourist_user.tourist_id
    r = client.patch(f"/api/tourists/{tid}/privacy", headers=tourist_headers,
                     json={"tracking_enabled": False, "data_retention_days": 30})
    assert r.status_code == 200
    assert r.json()["tracking_enabled"] is False
    assert r.json()["data_retention_days"] == 30


def test_delete_location_history_purges_pings(client, tourist_headers, tourist_user, db):
    tid = tourist_user.tourist_id
    process_ping(db, db.get(Tourist, tid), 26.14, 91.73, speed_kmh=5)
    assert db.query(LocationPing).filter(LocationPing.tourist_id == tid).count() > 0

    r = client.delete(f"/api/tourists/{tid}/location-history", headers=tourist_headers)
    assert r.status_code == 200
    assert r.json()["pings_deleted"] > 0
    assert db.query(LocationPing).filter(LocationPing.tourist_id == tid).count() == 0


def test_privacy_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Not Me")
    r = client.get(f"/api/tourists/{other.id}/privacy", headers=tourist_headers)
    assert r.status_code == 403


def test_retention_tick_purges_pings_past_window(db):
    t = make_tourist(db)
    t.trip_end = utc_now() - timedelta(days=200)
    t.data_retention_days = 90
    db.add(LocationPing(tourist_id=t.id, lat=1.0, lng=1.0, speed_kmh=1.0))
    db.commit()

    deleted = tick_retention_purge(db)
    assert deleted >= 1
    assert db.query(LocationPing).filter(LocationPing.tourist_id == t.id).count() == 0


def test_retention_tick_leaves_recent_pings_alone(db):
    t = make_tourist(db)  # trip_end is in the future by default -- nothing to purge
    db.add(LocationPing(tourist_id=t.id, lat=1.0, lng=1.0, speed_kmh=1.0))
    db.commit()

    tick_retention_purge(db)
    assert db.query(LocationPing).filter(LocationPing.tourist_id == t.id).count() == 1
