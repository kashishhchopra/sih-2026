"""Disaster & Weather Alert Feeds (services/disaster.py)."""
import pytest

from app.models.alert import Alert
from app.models.disaster import DisasterAdvisory
from app.services import disaster as disaster_module
from app.services import feeds, weather
from app.services.disaster import (
    _daily_seed,
    _instructions_for,
    _title_for,
    _weather_hazard_for_conditions,
    affected_tourist_count,
    notify_tourist_of_active_disasters,
    simulate_advisories,
    tick_disaster_feed,
    weather_condition_advisories,
)
from app.services.geo import zone_centroid
from tests.conftest import make_tourist, make_zone


@pytest.fixture(autouse=True)
def _isolate_feed_cache(tmp_path, monkeypatch):
    """feeds._memory_cache is a module-level global (by design -- shared
    across requests in the real app), and fetch_with_snapshot also persists
    to a real on-disk cache directory -- both would otherwise leak a
    "disaster_cap" payload across tests and even across test runs."""
    monkeypatch.setattr(feeds.settings, "FEED_CACHE_DIR", str(tmp_path))
    feeds.clear_cache()
    yield
    feeds.clear_cache()


def test_daily_seed_is_deterministic():
    assert _daily_seed(1, "flood") == _daily_seed(1, "flood")


def test_simulate_advisories_only_for_hazard_prone_zones(db):
    low = make_zone(db, name="Calm Park", risk="low")
    restricted = make_zone(db, name="Danger Zone", risk="restricted", lat=27.0, lng=92.0)
    candidates = simulate_advisories([low, restricted])
    assert all(c["zone_id"] != low.id for c in candidates)


def test_tick_disaster_feed_creates_and_notifies(db, monkeypatch):
    zone = make_zone(db, name="Flood Prone", risk="restricted", lat=26.165, lng=91.75, d=0.02)
    t = make_tourist(db, lat=26.165, lng=91.75)  # inside the zone

    # Force a deterministic "always fires" seed so this test isn't at the
    # mercy of the daily hash landing on the wrong bucket.
    monkeypatch.setattr("app.services.disaster._daily_seed", lambda zone_id, hazard: 0)

    result = tick_disaster_feed(db)
    assert result["created"]
    advisory = db.get(DisasterAdvisory, result["created"][0])
    assert advisory.zone_id == zone.id
    assert advisory.active is True

    alert = db.query(Alert).filter(Alert.type == "disaster", Alert.tourist_id == t.id).first()
    assert alert is not None


def test_tick_disaster_feed_expires_no_longer_indicated(db, monkeypatch):
    zone = make_zone(db, name="Was Flood Prone", risk="restricted", lat=26.165, lng=91.75, d=0.02)
    db.add(DisasterAdvisory(zone_id=zone.id, hazard_type="flood", severity="critical",
                            message="old", active=True))
    db.commit()

    # Nothing simulates as active now.
    monkeypatch.setattr("app.services.disaster.simulate_advisories", lambda zones: [])
    result = tick_disaster_feed(db)
    assert result["expired"]


# ---------------------------------------------------------------- real CAP feed
def test_tick_uses_simulator_when_no_provider_configured(db, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.disaster.fetch_real_feed_candidates",
                        lambda zones: calls.append(1))
    tick_disaster_feed(db)
    assert calls == []  # never even attempted -- DISASTER_FEED_PROVIDER is "" by default


def test_tick_uses_real_feed_when_configured(db, monkeypatch):
    from app.core.config import settings

    zone = make_zone(db, name="Real Feed Zone", risk="high", lat=26.165, lng=91.75, d=0.02)
    monkeypatch.setattr(settings, "DISASTER_FEED_PROVIDER", "cap")
    monkeypatch.setattr(
        "app.services.disaster.fetch_real_feed_candidates",
        lambda zones: [{"zone_id": zone.id, "hazard_type": "flood", "severity": "critical",
                        "message": "real advisory", "source": "cap:live",
                        "external_id": "NWS-123", "area_desc": "Test Area"}],
    )
    result = tick_disaster_feed(db)
    assert result["created"]
    advisory = db.get(DisasterAdvisory, result["created"][0])
    assert advisory.external_id == "NWS-123"
    assert advisory.area_desc == "Test Area"
    assert advisory.source == "cap:live"


def test_fetch_real_feed_candidates_returns_none_when_no_url_configured():
    from app.services.disaster import fetch_real_feed_candidates

    assert fetch_real_feed_candidates([]) is None


def test_fetch_real_feed_candidates_matches_alerts_onto_zones(db, monkeypatch):
    from app.core.config import settings
    from app.services import disaster as disaster_module
    from app.services.disaster import fetch_real_feed_candidates

    zone = make_zone(db, name="Matched Zone", risk="high", lat=26.165, lng=91.75, d=0.02)
    monkeypatch.setattr(settings, "DISASTER_FEED_URL", "https://example.test/cap")
    monkeypatch.setattr(disaster_module, "_fetch_cap_xml", lambda: "<fake-xml/>")
    monkeypatch.setattr(disaster_module.cap, "parse_cap_feed", lambda xml: [{
        "external_id": "X-1", "hazard_type": "flood", "severity": "high",
        "message": "test flood", "area_desc": "Test Area",
        "polygon": [[26.10, 91.65], [26.10, 91.85], [26.25, 91.85], [26.25, 91.65]],
    }])

    candidates = fetch_real_feed_candidates([zone])
    assert len(candidates) == 1
    assert candidates[0]["zone_id"] == zone.id
    assert candidates[0]["external_id"] == "X-1"
    assert candidates[0]["source"].startswith("cap:")


def test_fetch_real_feed_candidates_returns_none_when_feed_fetch_fails(monkeypatch):
    from app.core.config import settings
    from app.services import disaster as disaster_module
    from app.services.disaster import fetch_real_feed_candidates

    monkeypatch.setattr(settings, "DISASTER_FEED_URL", "https://example.test/cap")
    monkeypatch.setattr(settings, "FEEDS_ENABLED", False)  # forces the snapshot/cache rungs, both empty here

    assert fetch_real_feed_candidates([]) is None


def test_fetch_real_feed_candidates_returns_none_on_malformed_feed(monkeypatch):
    from app.core.config import settings
    from app.services import disaster as disaster_module
    from app.services.disaster import fetch_real_feed_candidates

    monkeypatch.setattr(settings, "DISASTER_FEED_URL", "https://example.test/cap")
    monkeypatch.setattr(disaster_module, "_fetch_cap_xml", lambda: "<not-valid-cap/>")
    monkeypatch.setattr(disaster_module.cap, "parse_cap_feed",
                        lambda xml: (_ for _ in ()).throw(ValueError("bad feed")))

    assert fetch_real_feed_candidates([]) is None


def test_fetch_cap_xml_uses_the_configured_url(monkeypatch):
    from app.core.config import settings
    from app.services.disaster import _fetch_cap_xml

    captured = {}

    class _FakeResponse:
        text = "<alert/>"
        def raise_for_status(self):
            pass

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _FakeResponse()

    monkeypatch.setattr(settings, "DISASTER_FEED_URL", "https://example.test/real-cap-feed")
    monkeypatch.setattr("httpx.get", fake_get)

    result = _fetch_cap_xml()
    assert result == "<alert/>"
    assert captured["url"] == "https://example.test/real-cap-feed"


def test_tick_falls_back_to_simulator_when_real_feed_unavailable(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DISASTER_FEED_PROVIDER", "cap")
    monkeypatch.setattr("app.services.disaster.fetch_real_feed_candidates", lambda zones: None)
    monkeypatch.setattr("app.services.disaster._daily_seed", lambda zone_id, hazard: 0)
    zone = make_zone(db, name="Fallback Zone", risk="restricted", lat=26.165, lng=91.75, d=0.02)

    result = tick_disaster_feed(db)
    assert result["created"]
    advisory = db.get(DisasterAdvisory, result["created"][0])
    assert advisory.zone_id == zone.id
    assert advisory.source == "simulated"


def test_active_advisories_for_tourist(db):
    from app.services.disaster import active_advisories_for_tourist
    zone = make_zone(db, name="Hazard Zone", risk="restricted", lat=26.165, lng=91.75, d=0.02)
    db.add(DisasterAdvisory(zone_id=zone.id, hazard_type="earthquake", severity="high",
                            message="shake", active=True))
    db.commit()
    t = make_tourist(db, lat=26.165, lng=91.75)

    advisories = active_advisories_for_tourist(db, t)
    assert len(advisories) == 1
    assert advisories[0].hazard_type == "earthquake"


# ---------------------------------------------------------------- endpoints
def test_list_disasters_endpoint(client, admin_headers, db):
    zone = make_zone(db)
    db.add(DisasterAdvisory(zone_id=zone.id, hazard_type="storm", severity="medium",
                            message="wind", active=True))
    db.commit()
    r = client.get("/api/disasters", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_list_disasters_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/disasters", headers=tourist_headers)
    assert r.status_code == 403


def test_tourist_disasters_endpoint(client, tourist_headers, tourist_user, db):
    zone = make_zone(db, lat=26.1445, lng=91.7362, d=0.02)
    db.add(DisasterAdvisory(zone_id=zone.id, hazard_type="flood", severity="high",
                            message="rising water", active=True))
    db.commit()
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/disasters", headers=tourist_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


# ---------------------------------------------------------------- zone_centroid
def test_zone_centroid_is_the_average_of_its_vertices(db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.02)
    lat, lng = zone_centroid(zone)
    assert lat == pytest.approx(26.165, abs=1e-6)
    assert lng == pytest.approx(91.75, abs=1e-6)


def test_zone_centroid_none_for_empty_polygon(db):
    zone = make_zone(db)
    zone.polygon = "[]"
    assert zone_centroid(zone) is None


# ---------------------------------------------------------------- title/instructions
def test_title_and_instructions_are_derived_from_hazard_type():
    assert _title_for("extreme_heat") == "Extreme Heat Advisory"
    assert "heat" in _instructions_for("extreme_heat").lower()
    # An unmapped hazard type still gets a non-empty generic instruction,
    # never a blank field.
    assert _instructions_for("meteor_strike")


# ---------------------------------------------------------------- real weather-condition hazards
@pytest.mark.parametrize("conditions,expected", [
    ({"weather_id": 211, "temp_c": 25.0, "wind_speed_ms": 2.0}, ("thunderstorm", "high")),
    ({"weather_id": 800, "temp_c": 46.0, "wind_speed_ms": 1.0}, ("extreme_heat", "critical")),
    ({"weather_id": 800, "temp_c": 43.0, "wind_speed_ms": 1.0}, ("extreme_heat", "high")),
    ({"weather_id": 800, "temp_c": -6.0, "wind_speed_ms": 1.0}, ("extreme_cold", "critical")),
    ({"weather_id": 800, "temp_c": 1.0, "wind_speed_ms": 1.0}, ("extreme_cold", "medium")),
    ({"weather_id": 502, "temp_c": 25.0, "wind_speed_ms": 1.0}, ("heavy_rain", "high")),
    ({"weather_id": 800, "temp_c": 25.0, "wind_speed_ms": 25.0}, ("storm", "high")),
    ({"weather_id": 741, "temp_c": 25.0, "wind_speed_ms": 1.0}, ("dense_fog", "medium")),
    ({"weather_id": 800, "temp_c": 25.0, "wind_speed_ms": 1.0}, None),  # clear, calm -- no hazard
])
def test_weather_hazard_for_conditions_thresholds(conditions, expected):
    assert _weather_hazard_for_conditions(conditions) == expected


def test_weather_condition_advisories_empty_without_api_key(db, monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "")
    zone = make_zone(db)
    assert weather_condition_advisories([zone]) == []


def test_weather_condition_advisories_no_fabrication_on_fetch_failure(db, monkeypatch):
    """No API key -> weather.fetch_current_conditions is never even asked;
    with a key but a failed/None response, still no candidate -- never a
    fabricated hazard standing in for missing real data."""
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")
    monkeypatch.setattr(disaster_module.weather, "fetch_current_conditions", lambda lat, lng: None)
    zone = make_zone(db)
    assert weather_condition_advisories([zone]) == []


def test_weather_condition_advisories_only_for_real_hazard_readings(db, monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")
    calm_zone = make_zone(db, name="Calm Zone", lat=10.0, lng=10.0, d=0.02)
    hot_zone = make_zone(db, name="Hot Zone", lat=20.0, lng=20.0, d=0.02)

    def fake_fetch(lat, lng):
        if (round(lat, 1), round(lng, 1)) == (20.0, 20.0):
            return {"weather_id": 800, "description": "clear sky", "temp_c": 46.0, "wind_speed_ms": 1.0}
        return {"weather_id": 800, "description": "clear sky", "temp_c": 25.0, "wind_speed_ms": 1.0}

    monkeypatch.setattr(disaster_module.weather, "fetch_current_conditions", fake_fetch)
    candidates = weather_condition_advisories([calm_zone, hot_zone])
    assert len(candidates) == 1
    assert candidates[0]["zone_id"] == hot_zone.id
    assert candidates[0]["hazard_type"] == "extreme_heat"
    assert candidates[0]["severity"] == "critical"
    assert candidates[0]["source"] == "openweathermap"


def test_tick_disaster_feed_merges_weather_condition_candidates(db, monkeypatch):
    zone = make_zone(db, name="Weather Hazard Zone", risk="low", lat=26.165, lng=91.75, d=0.02)
    monkeypatch.setattr(disaster_module.settings, "OPENWEATHER_API_KEY", "fake-key")
    monkeypatch.setattr(
        disaster_module.weather, "fetch_current_conditions",
        lambda lat, lng: {"weather_id": 211, "description": "thunderstorm", "temp_c": 28.0, "wind_speed_ms": 3.0},
    )
    result = tick_disaster_feed(db)
    advisory = db.get(DisasterAdvisory, result["created"][0])
    assert advisory.zone_id == zone.id
    assert advisory.hazard_type == "thunderstorm"
    assert advisory.source == "openweathermap"
    assert advisory.title == "Thunderstorm Advisory"
    assert advisory.instructions
    assert advisory.latitude == pytest.approx(26.165, abs=1e-6)
    assert advisory.longitude == pytest.approx(91.75, abs=1e-6)


# ---------------------------------------------------------------- zone-entry notification
def test_notify_tourist_of_active_disasters_on_zone_entry(db):
    """A tourist entering a zone with an *already active* advisory (the
    common case -- issued before they arrived) must still be notified, not
    only tourists present at the moment tick_disaster_feed created it."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.02)
    advisory = DisasterAdvisory(zone_id=zone.id, hazard_type="flood", severity="high",
                                message="rising water", active=True)
    db.add(advisory)
    db.commit()
    db.refresh(advisory)

    t = make_tourist(db, lat=26.165, lng=91.75)
    notified = notify_tourist_of_active_disasters(db, t, [zone])
    assert notified == [advisory.id]

    alert = db.query(Alert).filter(Alert.tourist_id == t.id, Alert.type == "disaster").first()
    assert alert is not None
    assert alert.disaster_advisory_id == advisory.id


def test_notify_tourist_of_active_disasters_does_not_duplicate(db):
    """Same tourist, same advisory, called again (e.g. the next GPS ping
    while still inside the zone) -- must not raise a second alert."""
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.02)
    advisory = DisasterAdvisory(zone_id=zone.id, hazard_type="flood", severity="high",
                                message="rising water", active=True)
    db.add(advisory)
    db.commit()
    db.refresh(advisory)

    t = make_tourist(db, lat=26.165, lng=91.75)
    first = notify_tourist_of_active_disasters(db, t, [zone])
    second = notify_tourist_of_active_disasters(db, t, [zone])
    assert first == [advisory.id]
    assert second == []

    count = db.query(Alert).filter(
        Alert.tourist_id == t.id, Alert.disaster_advisory_id == advisory.id,
    ).count()
    assert count == 1


def test_notify_tourist_of_active_disasters_no_zones_no_op(db):
    t = make_tourist(db)
    assert notify_tourist_of_active_disasters(db, t, []) == []


def test_process_ping_notifies_tourist_entering_already_active_advisory_zone(db):
    """End-to-end through the real GPS-ping pipeline (services/monitoring.py)
    -- not just the disaster-service function in isolation."""
    from app.services.monitoring import process_ping

    zone = make_zone(db, risk="low", lat=26.165, lng=91.75, d=0.02)
    advisory = DisasterAdvisory(zone_id=zone.id, hazard_type="storm", severity="high",
                                message="high winds", active=True)
    db.add(advisory)
    db.commit()
    db.refresh(advisory)

    t = make_tourist(db, lat=10.0, lng=10.0)  # starts outside the zone
    result = process_ping(db, t, 26.165, 91.75)  # moves inside it
    assert "disaster" in result["alerts_raised"]

    alert = db.query(Alert).filter(Alert.tourist_id == t.id, Alert.type == "disaster").first()
    assert alert is not None
    assert alert.disaster_advisory_id == advisory.id


# ---------------------------------------------------------------- affected_tourist_count
def test_affected_tourist_count(db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.02)
    advisory = DisasterAdvisory(zone_id=zone.id, hazard_type="flood", severity="high",
                                message="rising water", active=True)
    db.add(advisory)
    db.commit()
    db.refresh(advisory)

    make_tourist(db, lat=26.165, lng=91.75)  # inside
    make_tourist(db, lat=10.0, lng=10.0)  # outside

    assert affected_tourist_count(db, advisory) == 1


# ---------------------------------------------------------------- police-network disaster summary
def test_disaster_summary_endpoint(client, admin_headers, db):
    zone = make_zone(db, name="Summary Zone", lat=26.165, lng=91.75, d=0.02)
    db.add(DisasterAdvisory(zone_id=zone.id, hazard_type="storm", severity="high",
                            message="wind", active=True))
    db.commit()
    make_tourist(db, lat=26.165, lng=91.75)

    r = client.get("/api/police-network/disaster-summary", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["zone_name"] == "Summary Zone"
    assert body[0]["affected_tourists"] == 1


def test_disaster_summary_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/police-network/disaster-summary", headers=tourist_headers)
    assert r.status_code == 403
