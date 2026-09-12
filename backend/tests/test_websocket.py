"""WebSocket live feed: connection management and authorization.

The feed carries tourist locations and PII, so it must be admin-only.
"""
import asyncio

import pytest

from app.websocket.manager import ConnectionManager, broadcast_sync


class FakeWS:
    def __init__(self, fail=False):
        self.sent, self.accepted, self.fail = [], False, fail

    async def accept(self):
        self.accepted = True

    async def send_text(self, payload):
        if self.fail:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


def test_connect_accepts_and_registers():
    m, ws = ConnectionManager(), FakeWS()
    asyncio.run(m.connect(ws))
    assert ws.accepted is True and ws in m.active


def test_disconnect_removes():
    m, ws = ConnectionManager(), FakeWS()
    asyncio.run(m.connect(ws))
    asyncio.run(m.disconnect(ws))
    assert ws not in m.active


def test_disconnect_is_idempotent():
    m, ws = ConnectionManager(), FakeWS()
    asyncio.run(m.disconnect(ws))  # never connected; must not raise


def test_broadcast_reaches_every_client():
    m, a, b = ConnectionManager(), FakeWS(), FakeWS()
    asyncio.run(m.connect(a))
    asyncio.run(m.connect(b))
    asyncio.run(m.broadcast({"event": "alert", "severity": "high"}))
    assert len(a.sent) == len(b.sent) == 1
    assert "alert" in a.sent[0]


def test_broadcast_prunes_dead_sockets():
    m, good, dead = ConnectionManager(), FakeWS(), FakeWS(fail=True)
    asyncio.run(m.connect(good))
    asyncio.run(m.connect(dead))
    asyncio.run(m.broadcast({"event": "alert"}))
    assert dead not in m.active and good in m.active


def test_broadcast_serialises_datetimes():
    from app.core.time import utc_now
    m, ws = ConnectionManager(), FakeWS()
    asyncio.run(m.connect(ws))
    asyncio.run(m.broadcast({"event": "alert", "at": utc_now()}))
    assert len(ws.sent) == 1  # default=str handled the datetime


def test_broadcast_sync_without_a_loop_is_a_noop():
    broadcast_sync({"event": "alert"})  # no bound loop, no clients: must not raise


# ---------------------------------------------------------------- authorization
def test_ws_rejects_missing_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws/alerts") as ws:
        ws.receive_json()


def test_ws_rejects_tourist_token(client, tourist_headers):
    from starlette.websockets import WebSocketDisconnect
    token = tourist_headers["Authorization"].split()[1]
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/ws/alerts?token={token}") as ws,
    ):
        ws.receive_json()


def test_ws_accepts_admin_token(client, admin_headers):
    token = admin_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        assert ws.receive_json()["event"] == "connected"
