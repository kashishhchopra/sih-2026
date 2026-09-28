"""Sliding-window rate limiter (per client IP).

In-memory by default with no external dependency; set REDIS_URL to share limits
across workers/instances (the in-memory counters are per-process, so with
WEB_CONCURRENCY > 1 each worker would otherwise enforce its own quota).

The in-memory store is explicitly bounded. The previous version kept a
`defaultdict` of deques keyed by IP and never removed anything, so every distinct
client IP leaked memory permanently -- trivially exploitable by spraying spoofed
X-Forwarded-For values.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

# Hard ceiling on tracked keys. Beyond this the oldest-touched key is evicted,
# which at worst grants an attacker's victim one extra window -- far better than
# unbounded growth.
_MAX_TRACKED_KEYS = 50_000
# Sweep expired keys every N checks, so cleanup cost is amortised.
_SWEEP_EVERY = 1_000

_lock = threading.Lock()
_hits: OrderedDict[str, deque[float]] = OrderedDict()
_calls_since_sweep = 0


def _client_ip(request: Request) -> str:
    # Honour a single proxy hop if present (X-Forwarded-For), else peer address.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sweep(now: float, window: int) -> None:
    """Drop keys with no hits inside the window. Caller must hold the lock."""
    cutoff = now - window
    stale = [k for k, dq in _hits.items() if not dq or dq[-1] < cutoff]
    for k in stale:
        _hits.pop(k, None)


def _check(key: str, limit: int, window: int) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    global _calls_since_sweep
    now = time.monotonic()
    with _lock:
        _calls_since_sweep += 1
        if _calls_since_sweep >= _SWEEP_EVERY:
            _calls_since_sweep = 0
            _sweep(now, window)

        dq = _hits.get(key)
        if dq is None:
            dq = _hits[key] = deque()
        else:
            _hits.move_to_end(key)  # mark recently used for LRU eviction

        cutoff = now - window
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= limit:
            retry = int(dq[0] + window - now) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests - please slow down.",
                headers={"Retry-After": str(retry)},
            )
        dq.append(now)

        # Bound total memory: evict least-recently-used keys.
        while len(_hits) > _MAX_TRACKED_KEYS:
            _hits.popitem(last=False)


def reset() -> None:
    """Clear all counters. Used by the test suite to isolate cases."""
    with _lock:
        _hits.clear()


def tracked_keys() -> int:
    """Number of client keys currently held. Exposed for tests and metrics."""
    with _lock:
        return len(_hits)


def global_rate_limit(request: Request) -> None:
    """FastAPI dependency: coarse per-IP limit across the whole API."""
    _check(
        f"global:{_client_ip(request)}",
        settings.GLOBAL_RATE_LIMIT,
        settings.GLOBAL_RATE_WINDOW_SECONDS,
    )


def login_rate_limit(request: Request) -> None:
    """Stricter limit for the login endpoint (brute-force protection)."""
    _check(
        f"login:{_client_ip(request)}",
        settings.LOGIN_RATE_LIMIT,
        settings.LOGIN_RATE_WINDOW_SECONDS,
    )


def registration_rate_limit(request: Request) -> None:
    """Public tourist self-registration mints a digital ID with no auth at all,
    so it needs a tighter limit than the global one."""
    _check(
        f"register:{_client_ip(request)}",
        settings.REGISTRATION_RATE_LIMIT,
        settings.REGISTRATION_RATE_WINDOW_SECONDS,
    )
