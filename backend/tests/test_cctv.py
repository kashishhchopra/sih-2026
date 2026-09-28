"""CCTV network (services/cctv.py, /api/cctv).

The theme running through these: a camera row must never be able to make
itself LIVE. Every live/offline assertion below goes through a probe result,
and the probe is monkeypatched rather than allowed to touch the network.
"""
import pytest

from app.models.police import Camera
from app.services import cctv
from tests.conftest import make_camera, make_station, make_zone


@pytest.fixture(autouse=True)
def _neutral_cctv_provider(monkeypatch):
    """Pin the provider settings for every test in this module.

    Without this these tests read whatever CCTV_* values happen to be in the
    developer's .env, so a machine with a real provider configured would see
    different results than CI -- the import tests silently imported nothing
    once a bbox was set locally. Tests that need a provider opt in instead.
    """
    monkeypatch.setattr(cctv.settings, "CCTV_PROVIDER", "")
    monkeypatch.setattr(cctv.settings, "CCTV_PROVIDER_URL", "")
    monkeypatch.setattr(cctv.settings, "CCTV_PROVIDER_BBOX", "")
    monkeypatch.setattr(cctv.settings, "CCTV_PROVIDER_MAX_CAMERAS", 40)


def _patch_probe(monkeypatch, result):
    monkeypatch.setattr(cctv, "probe_stream", lambda url, stream_type: result)


# ---------------- retrieval & auth ----------------

def test_empty_network_is_a_valid_answer(client, admin_headers):
    r = client.get("/api/cctv", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["cameras"] == []
    assert body["summary"]["total"] == 0
    # An empty directory is not a misconfigured provider -- the UI needs to
    # tell those apart.
    assert body["summary"]["provider_configured"] is False


def test_requires_authentication(client):
    assert client.get("/api/cctv").status_code == 401


def test_tourist_cannot_read_camera_feeds(client, tourist_headers, db):
    make_camera(db)
    assert client.get("/api/cctv", headers=tourist_headers).status_code == 403


def test_responder_can_read_camera_feeds(client, responder_headers, db):
    make_camera(db, label="Gate Cam")
    r = client.get("/api/cctv", headers=responder_headers)
    assert r.status_code == 200
    assert r.json()["cameras"][0]["label"] == "Gate Cam"


# ---------------- status is probed, never assumed ----------------

def test_camera_with_no_stream_is_never_live(client, admin_headers, db):
    make_camera(db, label="Directory Only", status="active")
    r = client.get("/api/cctv", headers=admin_headers)
    cam = r.json()["cameras"][0]
    # status="active" in the DB, but with no feed it cannot be LIVE.
    assert cam["status"] == "active"
    assert cam["connection"] == "no_stream"


def test_live_only_when_the_probe_says_so(client, admin_headers, db, monkeypatch):
    make_camera(db, stream_url="https://example.org/feed.m3u8", stream_type="hls")
    _patch_probe(monkeypatch, cctv.LIVE)
    r = client.get("/api/cctv", headers=admin_headers)
    assert r.json()["cameras"][0]["connection"] == "live"
    assert r.json()["summary"]["live"] == 1


def test_unreachable_stream_reports_offline(client, admin_headers, db, monkeypatch):
    make_camera(db, stream_url="https://example.org/feed.m3u8", stream_type="hls")
    _patch_probe(monkeypatch, cctv.OFFLINE)
    r = client.get("/api/cctv", headers=admin_headers)
    assert r.json()["cameras"][0]["connection"] == "offline"
    assert r.json()["summary"]["offline"] == 1


def test_disabled_camera_reports_disabled_not_offline(client, admin_headers, db, monkeypatch):
    make_camera(db, status="offline", stream_url="https://example.org/f.m3u8",
                stream_type="hls")
    _patch_probe(monkeypatch, cctv.LIVE)  # even if the stream would answer
    r = client.get("/api/cctv", headers=admin_headers)
    assert r.json()["cameras"][0]["connection"] == "disabled"


def test_rtsp_is_reported_unplayable_rather_than_live(db):
    # No browser plays RTSP directly; claiming LIVE would render a blank box.
    assert cctv.probe_stream("rtsp://cam.example.org/stream", "rtsp") == cctv.UNPLAYABLE


def test_status_endpoint_rechecks_one_camera(client, admin_headers, db, monkeypatch):
    cam = make_camera(db, stream_url="https://example.org/f.m3u8", stream_type="hls")
    _patch_probe(monkeypatch, cctv.OFFLINE)
    assert client.get(f"/api/cctv/{cam.id}/status",
                      headers=admin_headers).json()["connection"] == "offline"
    # Camera comes back -> forcing a re-probe reflects that without a restart.
    _patch_probe(monkeypatch, cctv.LIVE)
    r = client.get(f"/api/cctv/{cam.id}/status?force=true", headers=admin_headers)
    assert r.json()["connection"] == "live"
    assert r.json()["last_checked_at"] is not None


def test_status_of_unknown_camera_is_404(client, admin_headers):
    assert client.get("/api/cctv/9999/status", headers=admin_headers).status_code == 404


def test_cached_status_avoids_reprobing_every_request(client, admin_headers, db, monkeypatch):
    make_camera(db, stream_url="https://example.org/f.m3u8", stream_type="hls")
    calls = []

    def counting_probe(url, stream_type):
        calls.append(url)
        return cctv.LIVE

    monkeypatch.setattr(cctv, "probe_stream", counting_probe)
    client.get("/api/cctv", headers=admin_headers)
    client.get("/api/cctv", headers=admin_headers)
    assert len(calls) == 1  # second read served from the cached probe


# ---------------- police-station relationship ----------------

def test_station_is_derived_from_the_zone_not_hardcoded(client, admin_headers, db):
    zone = make_zone(db, name="Market Zone")
    station = make_station(db, name="Market PS", zone_id=zone.id)
    make_camera(db, label="Market Cam", zone_id=zone.id)
    cam = client.get("/api/cctv", headers=admin_headers).json()["cameras"][0]
    assert cam["assigned_station_id"] == station.id


def test_explicit_assignment_overrides_the_zone_derivation(client, admin_headers, db):
    zone = make_zone(db, name="Zone A")
    make_station(db, name="Zone A PS", zone_id=zone.id)
    other = make_station(db, name="Special Ops PS", zone_id=None)
    make_camera(db, zone_id=zone.id, assigned_station_id=other.id)
    cam = client.get("/api/cctv", headers=admin_headers).json()["cameras"][0]
    assert cam["assigned_station_id"] == other.id


def test_camera_outside_any_zone_has_no_station(client, admin_headers, db):
    make_camera(db, zone_id=None)
    cam = client.get("/api/cctv", headers=admin_headers).json()["cameras"][0]
    assert cam["assigned_station_id"] is None


# ---------------- filtering ----------------

def test_filter_by_station(client, admin_headers, db):
    z1, z2 = make_zone(db, name="Z1"), make_zone(db, name="Z2", lat=26.2)
    s1 = make_station(db, name="PS1", zone_id=z1.id)
    make_station(db, name="PS2", zone_id=z2.id)
    make_camera(db, label="C1", zone_id=z1.id)
    make_camera(db, label="C2", zone_id=z2.id)
    r = client.get(f"/api/cctv?station_id={s1.id}", headers=admin_headers)
    labels = [c["label"] for c in r.json()["cameras"]]
    assert labels == ["C1"]


def test_search_matches_label(client, admin_headers, db):
    make_camera(db, label="Railway Station Approach")
    make_camera(db, label="Riverfront Promenade")
    r = client.get("/api/cctv?q=railway", headers=admin_headers)
    assert [c["label"] for c in r.json()["cameras"]] == ["Railway Station Approach"]


def test_filter_by_connection_state(client, admin_headers, db, monkeypatch):
    make_camera(db, label="Streaming", stream_url="https://example.org/a.m3u8",
                stream_type="hls")
    make_camera(db, label="Directory Only")
    _patch_probe(monkeypatch, cctv.LIVE)
    r = client.get("/api/cctv?connection=live", headers=admin_headers)
    assert [c["label"] for c in r.json()["cameras"]] == ["Streaming"]


def test_filter_by_zone(client, admin_headers, db):
    z = make_zone(db, name="Zoned")
    make_camera(db, label="In Zone", zone_id=z.id)
    make_camera(db, label="No Zone")
    r = client.get(f"/api/cctv?zone_id={z.id}", headers=admin_headers)
    assert [c["label"] for c in r.json()["cameras"]] == ["In Zone"]


# ---------------- security ----------------

def test_stream_credentials_are_stripped_before_leaving_the_backend(client, admin_headers, db):
    make_camera(db, stream_url="rtsp://operator:s3cret@cam.example.org/live",
                stream_type="rtsp")
    cam = client.get("/api/cctv", headers=admin_headers).json()["cameras"][0]
    assert "s3cret" not in cam["stream_url"]
    assert "operator" not in cam["stream_url"]
    assert cam["stream_url"] == "rtsp://cam.example.org/live"


def test_strip_credentials_leaves_a_clean_url_untouched():
    url = "https://cams.example.org/plaza/index.m3u8"
    assert cctv.strip_credentials(url) == url


# ---------------- provider import ----------------

def test_refresh_without_a_provider_reports_not_configured(client, admin_headers):
    r = client.post("/api/cctv/refresh", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["imported"] == 0  # nothing invented to fill the grid


def test_refresh_requires_admin(client, responder_headers):
    assert client.post("/api/cctv/refresh", headers=responder_headers).status_code == 403


def test_provider_import_upserts_instead_of_duplicating(db, monkeypatch):
    record = {"name": "Plaza Cam", "latitude": 26.15, "longitude": 91.74,
              "streamUrl": "https://cams.example.org/plaza/index.m3u8",
              "attribution": "Example Open Data"}
    monkeypatch.setattr(cctv, "_provider_records", lambda: [record])
    first = cctv.import_from_provider(db)
    second = cctv.import_from_provider(db)
    assert first["imported"] == 1
    assert second["imported"] == 0 and second["updated"] == 1
    assert db.query(Camera).count() == 1
    cam = db.query(Camera).first()
    assert cam.attribution == "Example Open Data"
    assert cam.stream_type == "hls"  # inferred from the .m3u8 URL


def test_provider_records_missing_coordinates_are_skipped(db, monkeypatch):
    monkeypatch.setattr(cctv, "_provider_records",
                        lambda: [{"name": "No Position", "streamUrl": "x.m3u8"}])
    result = cctv.import_from_provider(db)
    assert result["imported"] == 0
    assert db.query(Camera).count() == 0


# ---------------- stream type handling ----------------

@pytest.mark.parametrize("url,expected", [
    ("https://x.example.org/live/index.m3u8", "hls"),
    ("https://x.example.org/cam.mp4", "mp4"),
    ("http://x.example.org/mjpg/video.mjpg", "mjpeg"),
    ("rtsp://x.example.org/stream", "rtsp"),
    ("https://x.example.org/page", "none"),
    (None, "none"),
])
def test_stream_type_inferred_from_url(url, expected):
    assert cctv.infer_stream_type(url) == expected


def test_operator_can_register_a_camera_with_a_real_stream(client, admin_headers):
    r = client.post("/api/police-network/cameras", headers=admin_headers, json={
        "label": "Main Gate", "lat": 26.15, "lng": 91.74,
        "stream_url": "https://cams.example.org/gate/index.m3u8",
        "stream_type": "hls", "feed_source": "City Traffic Authority",
    })
    assert r.status_code == 201
    assert r.json()["stream_type"] == "hls"
    assert r.json()["feed_source"] == "City Traffic Authority"


def test_unknown_stream_type_is_rejected(client, admin_headers):
    r = client.post("/api/police-network/cameras", headers=admin_headers, json={
        "label": "Bad", "lat": 26.15, "lng": 91.74, "stream_type": "magic",
    })
    assert r.status_code == 422


def test_import_skips_sources_that_do_not_answer(db, monkeypatch):
    # An open feed lists plenty of cameras that no longer respond; importing
    # those would fill the console with rows that can only read OFFLINE.
    monkeypatch.setattr(cctv, "_provider_records", lambda: [
        {"name": "Working", "latitude": 26.1, "longitude": 91.7,
         "streamUrl": "https://cams.example.org/ok/index.m3u8"},
        {"name": "Dead", "latitude": 26.2, "longitude": 91.8,
         "streamUrl": "https://cams.example.org/dead/index.m3u8"},
    ])
    monkeypatch.setattr(cctv, "probe_stream",
                        lambda url, t: cctv.OFFLINE if "dead" in url else cctv.LIVE)
    result = cctv.import_from_provider(db)
    assert result["imported"] == 1
    assert "not reachable" in result["detail"]
    assert [c.label for c in db.query(Camera).all()] == ["Working"]


def test_import_honours_the_area_of_responsibility_bbox(db, monkeypatch):
    monkeypatch.setattr(cctv, "_provider_records", lambda: [
        {"name": "In Area", "latitude": 26.14, "longitude": 91.73, "streamUrl": None},
        {"name": "Far Away", "latitude": 34.05, "longitude": -118.24, "streamUrl": None},
    ])
    monkeypatch.setattr(cctv.settings, "CCTV_PROVIDER_BBOX", "26.0,91.0,27.0,92.0")
    cctv.import_from_provider(db)
    assert [c.label for c in db.query(Camera).all()] == ["In Area"]


def test_import_refuses_a_feed_entry_carrying_credentials(db, monkeypatch):
    # Real open camera datasets do leak operator RTSP credentials; those are
    # somebody's private camera, not a public feed.
    monkeypatch.setattr(cctv, "_provider_records", lambda: [
        {"name": "Private", "latitude": 26.1, "longitude": 91.7,
         "streamUrl": "rtsp://admin:hunter2@10.53.56.67:554/"},
    ])
    result = cctv.import_from_provider(db)
    assert result["imported"] == 0
    assert db.query(Camera).count() == 0


def test_listing_does_not_wait_on_a_slow_camera(client, admin_headers, db, monkeypatch):
    """Regression: the console sat on "Loading CCTV Network…" for ~16s.

    The listing probed cameras one after another inside the request, so the
    dashboard waited on the sum of every camera's timeout. Probing is now
    parallel and deadline-bounded.
    """
    import time

    for i in range(6):
        make_camera(db, label=f"Slow {i}",
                    stream_url=f"https://example.org/{i}.m3u8", stream_type="hls")

    def slow_probe(url, stream_type):
        time.sleep(0.4)
        return cctv.LIVE

    monkeypatch.setattr(cctv, "probe_stream", slow_probe)
    started = time.monotonic()
    r = client.get("/api/cctv", headers=admin_headers)
    elapsed = time.monotonic() - started
    assert r.status_code == 200
    # Sequentially this would be ~2.4s; in parallel it is roughly one probe.
    assert elapsed < 1.5, f"listing took {elapsed:.2f}s -- probing is serial again"


def test_cameras_that_cannot_be_probed_in_time_do_not_block_the_listing(
        client, admin_headers, db, monkeypatch):
    make_camera(db, label="Hangs", stream_url="https://example.org/h.m3u8",
                stream_type="hls")

    def hanging_probe(url, stream_type):
        import time
        time.sleep(5)
        return cctv.LIVE

    monkeypatch.setattr(cctv, "probe_stream", hanging_probe)
    monkeypatch.setattr(cctv.settings, "CCTV_LIST_PROBE_DEADLINE_SECONDS", 0.3)
    r = client.get("/api/cctv", headers=admin_headers)
    assert r.status_code == 200
    # Still answers, reporting the camera as not-yet-known rather than hanging.
    assert r.json()["cameras"][0]["connection"] == "unknown"


def test_cameras_with_a_live_feed_are_listed_before_coverage_only_records(
        client, admin_headers, db, monkeypatch):
    # A surveillance console is for watching cameras: feedless directory
    # rows must not push the live ones below the fold.
    make_camera(db, label="Coverage Only")
    make_camera(db, label="Has Feed", stream_url="https://example.org/a.m3u8",
                stream_type="hls")
    _patch_probe(monkeypatch, cctv.LIVE)
    labels = [c["label"] for c in
              client.get("/api/cctv", headers=admin_headers).json()["cameras"]]
    assert labels == ["Has Feed", "Coverage Only"]


# ---------------- "camera unavailable" notice cards ----------------

def _jpeg(colour_fn, size=(64, 64)) -> bytes:
    """Build a real JPEG in memory for the image-content checks."""
    import io

    from PIL import Image
    img = Image.new("RGB", size)
    img.putdata([colour_fn(i) for i in range(size[0] * size[1])])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_flat_notice_card_is_recognised_as_not_a_camera_view():
    # What a road-camera network serves when a camera is down: a flat card
    # reading "Temporarily Unavailable". It is a valid 200 JPEG, so
    # reachability alone would call it LIVE.
    flat = _jpeg(lambda i: (255, 255, 255))
    assert cctv._looks_like_notice_card(flat) is True


def test_a_real_photograph_is_not_mistaken_for_a_notice_card():
    # Textured frame (the snowy-whiteout false positive this guards against
    # still has per-pixel variation; a synthetic card does not).
    import random
    rng = random.Random(7)
    noisy = _jpeg(lambda i: (rng.randint(180, 255),) * 3)
    assert cctv._looks_like_notice_card(noisy) is False


def test_unreadable_bytes_do_not_claim_a_notice_card():
    assert cctv._looks_like_notice_card(b"not an image") is False


def test_camera_serving_a_notice_card_is_not_reported_live(client, admin_headers, db, monkeypatch):
    make_camera(db, label="Down For Construction",
                stream_url="https://cams.example.org/x.jpg", stream_type="jpeg")
    _patch_probe(monkeypatch, cctv.UNAVAILABLE)
    body = client.get("/api/cctv", headers=admin_headers).json()
    assert body["cameras"][0]["connection"] == "unavailable"
    assert body["summary"]["live"] == 0
    assert body["summary"]["unavailable"] == 1


def test_import_skips_cameras_the_source_marks_unavailable(db, monkeypatch):
    monkeypatch.setattr(cctv, "_provider_records", lambda: [
        {"name": "Notice Card", "latitude": 26.1, "longitude": 91.7,
         "streamUrl": "https://cams.example.org/down.jpg", "format": "IMAGE_STREAM"},
    ])
    monkeypatch.setattr(cctv, "probe_stream", lambda url, t: cctv.UNAVAILABLE)
    assert cctv.import_from_provider(db)["imported"] == 0
    assert db.query(Camera).count() == 0


# ---------------- deleting a camera ----------------

def test_admin_can_delete_a_camera(client, admin_headers, db):
    cam = make_camera(db, label="Dead Source")
    r = client.delete(f"/api/cctv/{cam.id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.get(Camera, cam.id) is None


def test_deleting_an_unknown_camera_is_404(client, admin_headers):
    assert client.delete("/api/cctv/9999", headers=admin_headers).status_code == 404


def test_deleting_a_camera_requires_admin(client, responder_headers, db):
    cam = make_camera(db)
    r = client.delete(f"/api/cctv/{cam.id}", headers=responder_headers)
    assert r.status_code == 403


def test_delete_removes_only_that_camera(client, admin_headers, db):
    keep = make_camera(db, label="Keep")
    gone = make_camera(db, label="Gone")
    client.delete(f"/api/cctv/{gone.id}", headers=admin_headers)
    labels = [c["label"] for c in
              client.get("/api/cctv", headers=admin_headers).json()["cameras"]]
    assert labels == ["Keep"]
