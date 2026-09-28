"""In-process WebSocket connection manager for real-time push.

Two channels:
  - `active`: the admin/control-room feed (unchanged) -- every event, for
    every tourist, since operators need the whole picture.
  - `tourist_conns`: per-tourist channels. A tourist's own geofence/anomaly/
    SOS events are pushed only to their own connection(s), never anyone
    else's, which is why this is keyed by tourist_id and kept separate from
    the admin broadcast rather than filtering client-side.

Before this, the tourist app had no socket at all and relied on its own
location-push responses to learn about alerts -- so a geofence warning only
appeared the next time the tourist's device happened to send a ping, not
when it actually happened.
"""
import asyncio
import contextlib
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self.tourist_conns: dict[int, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once at app startup so sync code can schedule onto this loop."""
        self._loop = loop

    # ---------------------------------------------------------------- admin feed
    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    # ---------------------------------------------------------------- per-tourist channel
    async def connect_tourist(self, ws: WebSocket, tourist_id: int) -> None:
        await ws.accept()
        async with self._lock:
            self.tourist_conns[tourist_id].append(ws)

    async def disconnect_tourist(self, ws: WebSocket, tourist_id: int) -> None:
        async with self._lock:
            conns = self.tourist_conns.get(tourist_id)
            if conns and ws in conns:
                conns.remove(ws)
                if not conns:
                    del self.tourist_conns[tourist_id]

    async def notify_tourist(self, tourist_id: int, message: dict[str, Any]) -> None:
        conns = list(self.tourist_conns.get(tourist_id, ()))
        if not conns:
            return
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect_tourist(ws, tourist_id)


manager = ConnectionManager()


def broadcast_sync(message: dict[str, Any]) -> None:
    """Fire-and-forget admin-feed broadcast callable from sync request handlers.

    FastAPI runs sync endpoints in a threadpool, so we schedule the coroutine onto
    the main event loop captured at startup (thread-safe). No-op if no loop/clients.
    """
    loop = manager._loop
    if loop is None or not manager.active:
        return
    with contextlib.suppress(RuntimeError):
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)


def notify_tourist_sync(tourist_id: int | None, message: dict[str, Any]) -> None:
    """Fire-and-forget push to one tourist's own channel(s)."""
    if tourist_id is None:
        return
    loop = manager._loop
    if loop is None or not manager.tourist_conns.get(tourist_id):
        return
    with contextlib.suppress(RuntimeError):
        asyncio.run_coroutine_threadsafe(manager.notify_tourist(tourist_id, message), loop)
