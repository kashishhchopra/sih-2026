"""Silent / Duress SOS (POST /tourists/{id}/duress-pin, POST /tourists/{id}/sos/duress)."""
from unittest.mock import patch

from app.models.incident import Incident
from tests.conftest import make_unit


def test_set_and_use_duress_pin_raises_silent_sos(client, tourist_headers, tourist_user, db):
    make_unit(db)
    tid = tourist_user.tourist_id
    set_r = client.post(f"/api/tourists/{tid}/duress-pin", headers=tourist_headers, json={"pin": "1234"})
    assert set_r.status_code == 200

    sos_r = client.post(f"/api/tourists/{tid}/sos/duress", headers=tourist_headers,
                        json={"pin": "1234", "lat": 26.14, "lng": 91.73, "message": "trapped"})
    assert sos_r.status_code == 200
    inc = db.get(Incident, sos_r.json()["incident_id"])
    assert inc.silent is True
    assert inc.severity == "critical"


def test_duress_sos_does_not_notify_own_device(client, tourist_headers, tourist_user, db):
    """A silent SOS must not push the '🚨 SOS' alert back to the tourist's own
    WebSocket channel -- that would defeat the entire point (someone watching
    the screen would see it)."""
    make_unit(db)
    tid = tourist_user.tourist_id
    client.post(f"/api/tourists/{tid}/duress-pin", headers=tourist_headers, json={"pin": "1234"})

    with patch("app.services.monitoring.notify_tourist_sync") as mock_notify, \
         patch("app.services.monitoring.broadcast_sync") as mock_broadcast:
        r = client.post(f"/api/tourists/{tid}/sos/duress", headers=tourist_headers,
                        json={"pin": "1234", "lat": 26.14, "lng": 91.73, "message": "trapped"})
        assert r.status_code == 200
        # The control room must still see it...
        sos_broadcasts = [c for c in mock_broadcast.call_args_list if c.args[0].get("type") == "sos"]
        assert sos_broadcasts
        # ...but the tourist's own device must not.
        sos_self_notifies = [c for c in mock_notify.call_args_list if c.args[1].get("type") == "sos"]
        assert sos_self_notifies == []


def test_regular_sos_still_notifies_own_device(client, tourist_headers, tourist_user, db):
    make_unit(db)
    tid = tourist_user.tourist_id
    with patch("app.services.monitoring.notify_tourist_sync") as mock_notify:
        client.post(f"/api/tourists/{tid}/sos", headers=tourist_headers,
                   json={"lat": 26.14, "lng": 91.73, "message": "help"})
        sos_self_notifies = [c for c in mock_notify.call_args_list if c.args[1].get("type") == "sos"]
        assert sos_self_notifies


def test_wrong_pin_rejected(client, tourist_headers, tourist_user):
    tid = tourist_user.tourist_id
    client.post(f"/api/tourists/{tid}/duress-pin", headers=tourist_headers, json={"pin": "1234"})
    r = client.post(f"/api/tourists/{tid}/sos/duress", headers=tourist_headers,
                    json={"pin": "9999", "lat": 26.14, "lng": 91.73, "message": "x"})
    assert r.status_code == 400


def test_duress_sos_without_pin_set_rejected(client, tourist_headers, tourist_user):
    tid = tourist_user.tourist_id
    r = client.post(f"/api/tourists/{tid}/sos/duress", headers=tourist_headers,
                    json={"pin": "1234", "lat": 26.14, "lng": 91.73, "message": "x"})
    assert r.status_code == 400


def test_regular_sos_is_not_silent(client, tourist_headers, tourist_user, db):
    make_unit(db)
    tid = tourist_user.tourist_id
    r = client.post(f"/api/tourists/{tid}/sos", headers=tourist_headers,
                    json={"lat": 26.14, "lng": 91.73, "message": "help"})
    inc = db.get(Incident, r.json()["incident_id"])
    assert inc.silent is False


def test_regular_sos_can_be_marked_silent(client, tourist_headers, tourist_user, db):
    make_unit(db)
    tid = tourist_user.tourist_id
    r = client.post(f"/api/tourists/{tid}/sos", headers=tourist_headers,
                    json={"lat": 26.14, "lng": 91.73, "message": "help", "silent": True})
    inc = db.get(Incident, r.json()["incident_id"])
    assert inc.silent is True
