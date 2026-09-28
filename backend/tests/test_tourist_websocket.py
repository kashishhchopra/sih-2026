"""Per-tourist WebSocket channel and connection manager scoping.

Before this, the socket was admin-only, so a tourist's own device learned
about a geofence/anomaly alert only by coincidence, the next time it happened
to POST a location ping. This channel pushes it the moment it happens.
"""
import asyncio

import pytest

from app.websocket.manager import ConnectionManager


class FakeWS:
    def __init__(self, fail=False):
        self.sent, self.accepted, self.fail = [], False, fail

    async def accept(self):
        self.accepted = True

    async def send_text(self, payload):
        if self.fail:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


def test_tourist_channel_is_isolated_per_tourist():
    m = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    asyncio.run(m.connect_tourist(a, tourist_id=1))
    asyncio.run(m.connect_tourist(b, tourist_id=2))

    asyncio.run(m.notify_tourist(1, {"event": "alert", "type": "geofence"}))
    assert len(a.sent) == 1
    assert len(b.sent) == 0


def test_tourist_channel_does_not_reach_the_admin_feed():
    m = ConnectionManager()
    admin_ws, tourist_ws = FakeWS(), FakeWS()
    asyncio.run(m.connect(admin_ws))
    asyncio.run(m.connect_tourist(tourist_ws, tourist_id=1))

    asyncio.run(m.notify_tourist(1, {"event": "alert"}))
    assert len(tourist_ws.sent) == 1
    assert len(admin_ws.sent) == 0


def test_multiple_devices_for_the_same_tourist_all_receive():
    m = ConnectionManager()
    phone, band = FakeWS(), FakeWS()
    asyncio.run(m.connect_tourist(phone, tourist_id=1))
    asyncio.run(m.connect_tourist(band, tourist_id=1))

    asyncio.run(m.notify_tourist(1, {"event": "alert"}))
    assert len(phone.sent) == len(band.sent) == 1


def test_notify_unknown_tourist_is_a_noop():
    m = ConnectionManager()
    asyncio.run(m.notify_tourist(999, {"event": "alert"}))  # must not raise


def test_disconnect_removes_only_that_tourists_socket():
    m = ConnectionManager()
    a, b = FakeWS(), FakeWS()
    asyncio.run(m.connect_tourist(a, tourist_id=1))
    asyncio.run(m.connect_tourist(b, tourist_id=1))
    asyncio.run(m.disconnect_tourist(a, tourist_id=1))

    asyncio.run(m.notify_tourist(1, {"event": "alert"}))
    assert len(a.sent) == 0
    assert len(b.sent) == 1


def test_last_disconnect_cleans_up_the_tourist_entry():
    m = ConnectionManager()
    ws = FakeWS()
    asyncio.run(m.connect_tourist(ws, tourist_id=1))
    asyncio.run(m.disconnect_tourist(ws, tourist_id=1))
    assert 1 not in m.tourist_conns


def test_notify_prunes_dead_sockets():
    m = ConnectionManager()
    dead, alive = FakeWS(fail=True), FakeWS()
    asyncio.run(m.connect_tourist(dead, tourist_id=1))
    asyncio.run(m.connect_tourist(alive, tourist_id=1))
    asyncio.run(m.notify_tourist(1, {"event": "alert"}))
    assert dead not in m.tourist_conns[1]
    assert alive in m.tourist_conns[1]


# ---------------------------------------------------------------- HTTP-level (route)
def test_ws_tourist_rejects_missing_token(client, tourist_user):
    from starlette.websockets import WebSocketDisconnect
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/ws/tourist/{tourist_user.tourist_id}") as ws,
    ):
        ws.receive_json()


def test_ws_tourist_rejects_a_different_tourists_token(client, db, tourist_headers):
    from starlette.websockets import WebSocketDisconnect

    from tests.conftest import make_tourist
    other = make_tourist(db, name="Someone Else")
    token = tourist_headers["Authorization"].split()[1]

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/ws/tourist/{other.id}?token={token}") as ws,
    ):
        ws.receive_json()


def test_ws_tourist_accepts_the_owning_tourist(client, tourist_user, tourist_headers):
    token = tourist_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/tourist/{tourist_user.tourist_id}?token={token}") as ws:
        assert ws.receive_json()["event"] == "connected"


def test_ws_tourist_accepts_admin_shadowing_any_tourist(client, tourist_user, admin_headers):
    token = admin_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/tourist/{tourist_user.tourist_id}?token={token}") as ws:
        assert ws.receive_json()["event"] == "connected"


def test_geofence_alert_is_pushed_to_the_tourists_own_channel(client, db, tourist_user, admin_headers):
    """End-to-end: a geofence alert raised by the monitoring pipeline must
    reach that tourist's own WebSocket connection."""
    from tests.conftest import make_zone

    make_zone(db, name="Old Market", risk="high", lat=26.165, lng=91.75)
    token = admin_headers["Authorization"].split()[1]

    with client.websocket_connect(f"/ws/tourist/{tourist_user.tourist_id}?token={token}") as ws:
        assert ws.receive_json()["event"] == "connected"
        client.post(
            f"/api/tourists/{tourist_user.tourist_id}/location",
            json={"lat": 26.165, "lng": 91.75, "speed_kmh": 3},
            headers=admin_headers,
        )
        # The ping is far from the tourist's default itinerary, so it may also
        # trigger a route-deviation/anomaly alert first; read until geofence
        # arrives rather than assuming it's the very first message.
        messages = [ws.receive_json() for _ in range(3)]
        geofence_msgs = [m for m in messages if m["type"] == "geofence"]
        assert len(geofence_msgs) == 1
        assert geofence_msgs[0]["tourist_id"] == tourist_user.tourist_id
