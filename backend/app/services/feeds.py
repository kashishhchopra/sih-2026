"""Shared fallback ladder for any external data feed used by this app.

Real deployments should never depend on network access to function -- a
demo venue may have none at all -- so every live feed (weather already had
its own version of this; disaster advisories and POI import use this shared
one) degrades through the same three rungs:

  1. live   -- fetch it now
  2. cache  -- the last successful live fetch, persisted to disk so it
               survives a restart (not committed to git)
  3. snapshot -- a committed, known-good example bundled with the app, so
               even a machine that has NEVER had network access still works

`source` is always returned alongside the payload so callers (and
ultimately the UI, see frontend/src/components/DataSourceBadge.jsx) can
show honestly which rung actually answered instead of pretending
everything is always live.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from app.core.config import settings

logger = logging.getLogger(__name__)

Source = Literal["live", "cache", "snapshot"]

_memory_cache: dict[str, tuple[Any, float]] = {}  # name -> (payload, expires_at)


def _cache_file(name: str) -> Path:
    cache_dir = Path(settings.FEED_CACHE_DIR)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{name}.json"


def _snapshot_file(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "snapshots" / f"{name}.json"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("feeds: could not read %s: %s", path, e)
        return None


def fetch_with_snapshot(
    name: str, fetcher: Callable[[], Any], *, ttl_seconds: int | None = None,
) -> tuple[Any, Source]:
    """Returns (payload, source). `fetcher` should return a JSON-serialisable
    value or raise/return None on failure -- any exception is treated as a
    failed fetch, never propagated (a flaky external feed must never break
    the request path)."""
    ttl = ttl_seconds if ttl_seconds is not None else settings.FEED_TIMEOUT_SECONDS
    now = time.monotonic()

    cached = _memory_cache.get(name)
    if cached and cached[1] > now:
        return cached[0], "cache"

    if settings.FEEDS_ENABLED:
        try:
            payload = fetcher()
        except Exception as e:  # noqa: BLE001 -- any live-feed failure falls through
            logger.warning("feeds: live fetch for %s failed: %s", name, e)
            payload = None

        if payload is not None:
            _memory_cache[name] = (payload, now + ttl)
            try:
                _cache_file(name).write_text(json.dumps(payload), encoding="utf-8")
            except OSError as e:
                logger.warning("feeds: could not persist cache for %s: %s", name, e)
            return payload, "live"

    disk_cached = _read_json(_cache_file(name))
    if disk_cached is not None:
        return disk_cached, "cache"

    snapshot = _read_json(_snapshot_file(name))
    if snapshot is not None:
        return snapshot, "snapshot"

    return None, "snapshot"


def clear_cache() -> None:
    _memory_cache.clear()
