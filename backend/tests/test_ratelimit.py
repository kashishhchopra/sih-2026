"""Rate limiter: correctness and the memory bound.

The store previously grew without limit (a defaultdict keyed by client IP that
was never pruned), so spraying spoofed X-Forwarded-For headers leaked memory
permanently. These tests pin the fix.
"""
import time

import pytest
from fastapi import HTTPException

from app.core import ratelimit


def test_allows_requests_under_the_limit():
    for _ in range(5):
        ratelimit._check("k", limit=5, window=60)


def test_blocks_over_the_limit():
    for _ in range(3):
        ratelimit._check("k", limit=3, window=60)
    with pytest.raises(HTTPException) as exc:
        ratelimit._check("k", limit=3, window=60)
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


def test_window_slides_and_frees_the_quota():
    ratelimit._check("k", limit=1, window=1)
    with pytest.raises(HTTPException):
        ratelimit._check("k", limit=1, window=1)
    time.sleep(1.05)
    ratelimit._check("k", limit=1, window=1)  # must not raise


def test_keys_are_independent():
    ratelimit._check("a", limit=1, window=60)
    ratelimit._check("b", limit=1, window=60)  # different key, own quota


def test_expired_keys_are_swept_away(monkeypatch):
    """Keys whose hits have aged out of the window must be reclaimed, not kept
    forever. Sweeping is amortised, so drive enough calls to trigger one."""
    monkeypatch.setattr(ratelimit, "_SWEEP_EVERY", 10)
    for i in range(10):
        ratelimit._check(f"stale-{i}", limit=100, window=1)
    assert ratelimit.tracked_keys() >= 10

    time.sleep(1.05)  # let every recorded hit fall outside the window
    for i in range(10):
        ratelimit._check(f"fresh-{i}", limit=100, window=1)

    assert ratelimit.tracked_keys() < 20, "stale keys were never reclaimed"


def test_store_never_exceeds_the_hard_cap(monkeypatch):
    monkeypatch.setattr(ratelimit, "_MAX_TRACKED_KEYS", 50)
    for i in range(500):
        ratelimit._check(f"ip-{i}", limit=100, window=3600)
    assert ratelimit.tracked_keys() <= 50


def test_disabled_limiter_is_a_no_op(monkeypatch):
    monkeypatch.setattr(ratelimit.settings, "RATE_LIMIT_ENABLED", False)
    for _ in range(1000):
        ratelimit._check("k", limit=1, window=60)
