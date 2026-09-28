"""Live -> cache -> snapshot fallback ladder (app/services/feeds.py)."""
import json

import pytest

from app.services import feeds


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(feeds.settings, "FEED_CACHE_DIR", str(tmp_path))
    feeds.clear_cache()
    yield
    feeds.clear_cache()


def test_live_fetch_succeeds_and_is_returned_as_live():
    payload, source = feeds.fetch_with_snapshot("t1", lambda: {"ok": True})
    assert payload == {"ok": True}
    assert source == "live"


def test_successful_live_fetch_is_served_from_memory_cache_on_next_call():
    calls = []

    def fetcher():
        calls.append(1)
        return {"n": len(calls)}

    first, src1 = feeds.fetch_with_snapshot("t2", fetcher, ttl_seconds=60)
    second, src2 = feeds.fetch_with_snapshot("t2", fetcher, ttl_seconds=60)
    assert src1 == "live"
    assert src2 == "cache"
    assert first == second
    assert len(calls) == 1


def test_fetcher_exception_falls_through_without_raising():
    def broken():
        raise RuntimeError("network down")

    payload, source = feeds.fetch_with_snapshot("t3", broken)
    assert source == "snapshot"
    assert payload is None  # no disk cache, no snapshot file for this name


def test_fetcher_returning_none_falls_through_the_same_way():
    payload, source = feeds.fetch_with_snapshot("t4", lambda: None)
    assert source == "snapshot"
    assert payload is None


def test_disk_cache_survives_a_cleared_memory_cache():
    feeds.fetch_with_snapshot("t5", lambda: {"v": 1}, ttl_seconds=60)
    feeds.clear_cache()  # memory cache gone, disk cache remains

    def broken():
        raise RuntimeError("now offline")

    payload, source = feeds.fetch_with_snapshot("t5", broken)
    assert source == "cache"
    assert payload == {"v": 1}


def test_feeds_disabled_skips_live_fetch_entirely(monkeypatch):
    monkeypatch.setattr(feeds.settings, "FEEDS_ENABLED", False)
    called = []
    payload, source = feeds.fetch_with_snapshot("t6", lambda: called.append(1))
    assert called == []
    assert source == "snapshot"


def test_falls_back_to_a_committed_snapshot_file(tmp_path, monkeypatch):
    # Point the snapshot lookup at a temp file standing in for the real
    # app/data/snapshots/<name>.json path.
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "t7.json").write_text(json.dumps({"from": "snapshot"}), encoding="utf-8")

    monkeypatch.setattr(feeds, "_snapshot_file", lambda name: snapshot_dir / f"{name}.json")

    def broken():
        raise RuntimeError("offline")

    payload, source = feeds.fetch_with_snapshot("t7", broken)
    assert source == "snapshot"
    assert payload == {"from": "snapshot"}
