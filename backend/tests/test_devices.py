"""IoT smart-band registration, device-key authentication, and telemetry."""
import pytest

from app.models.alert import Alert
from app.models.incident import Incident
from tests.conftest import make_tourist


@pytest.fixture
def registered_device(client, admin_headers, db):
    t = make_tourist(db)
    r = client.post("/api/devices/register",
                    json={"tourist_id": t.id, "device_id": "BAND-001",
                          "firmware_version": "1.2.3"},
                    headers=admin_headers)
    assert r.status_code == 201
    return {"tourist": t, "device_id": "BAND-001", "api_key": r.json()["api_key"]}


def test_registration_returns_the_key_exactly_once(registered_device):
    assert len(registered_device["api_key"]) > 20


def test_registration_requires_admin(client, tourist_headers, tourist_user):
    r = client.post("/api/devices/register",
                    json={"tourist_id": tourist_user.tourist_id, "device_id": "BAND-X"},
                    headers=tourist_headers)
    assert r.status_code == 403


def test_registration_rejects_unknown_tourist(client, admin_headers):
    r = client.post("/api/devices/register",
                    json={"tourist_id": 9999, "device_id": "BAND-UNKNOWN"}, headers=admin_headers)
    assert r.status_code == 404


def test_duplicate_device_id_rejected(client, admin_headers, registered_device):
    r = client.post("/api/devices/register",
                    json={"tourist_id": registered_device["tourist"].id,
                          "device_id": "BAND-001"}, headers=admin_headers)
    assert r.status_code == 400


def test_telemetry_requires_the_device_key(client, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 3})
    assert r.status_code in (401, 422)  # 422 if header entirely missing


def test_telemetry_rejects_the_wrong_key(client, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 3},
                    headers={"X-Device-Key": "not-the-real-key"})
    assert r.status_code == 401


def test_telemetry_rejects_an_unknown_device(client):
    r = client.post("/api/devices/NOT-REGISTERED/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 3},
                    headers={"X-Device-Key": "anything"})
    assert r.status_code == 401


def test_valid_telemetry_updates_location_and_heartbeat(client, registered_device, db):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.15, "lng": 91.74, "speed_kmh": 4,
                          "heart_rate_bpm": 75, "battery_pct": 88},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert r.status_code == 200
    assert r.json()["safety_score"] is not None

    from app.models.device import Device
    device = db.query(Device).filter_by(device_id=registered_device["device_id"]).one()
    assert device.battery_pct == 88
    assert device.last_heartbeat is not None
    assert device.is_online is True


def test_high_heart_rate_raises_health_anomaly(client, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 2,
                          "heart_rate_bpm": 190},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert "health_anomaly" in r.json()["alerts_raised"]


def test_low_heart_rate_raises_health_anomaly(client, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 0,
                          "heart_rate_bpm": 30},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert "health_anomaly" in r.json()["alerts_raised"]


def test_normal_heart_rate_does_not_alert(client, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 2,
                          "heart_rate_bpm": 72},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert "health_anomaly" not in r.json()["alerts_raised"]


def test_missing_heart_rate_does_not_alert(client, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 2},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert "health_anomaly" not in r.json()["alerts_raised"]


def test_fall_detected_opens_a_critical_incident(client, registered_device, db):
    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 0,
                          "fall_detected": True},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert "fall_detected" in r.json()["alerts_raised"]
    inc = db.query(Incident).filter_by(type="fall_detected").one()
    assert inc.severity == "critical"
    assert db.query(Alert).filter_by(type="fall_detected").count() == 1


def test_sos_button_triggers_full_sos_flow(client, registered_device, db):
    from tests.conftest import make_unit
    make_unit(db)

    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 0,
                          "sos_pressed": True},
                    headers={"X-Device-Key": registered_device["api_key"]})
    body = r.json()
    assert "sos" in body
    assert body["sos"]["nearest_unit"] is not None

    db.refresh(registered_device["tourist"])
    assert registered_device["tourist"].status == "sos"


def test_deactivated_device_cannot_submit_telemetry(client, admin_headers, registered_device):
    r = client.post(f"/api/devices/{registered_device['device_id']}/deactivate",
                    headers=admin_headers)
    assert r.status_code == 200 and r.json()["active"] is False

    r = client.post(f"/api/devices/{registered_device['device_id']}/telemetry",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 2},
                    headers={"X-Device-Key": registered_device["api_key"]})
    assert r.status_code == 401


def test_list_devices_requires_admin(client, tourist_headers):
    assert client.get("/api/devices", headers=tourist_headers).status_code == 403


def test_list_devices_shows_offline_status(client, admin_headers, db):
    from app.models.device import Device
    t = make_tourist(db)
    db.add(Device(device_id="OFFLINE-1", tourist_id=t.id, hashed_key="x",
                  last_heartbeat=None))
    db.commit()

    devices = client.get("/api/devices", headers=admin_headers).json()
    row = next(d for d in devices if d["device_id"] == "OFFLINE-1")
    assert row["is_online"] is False
