"""Maps service: demo-mode geocoding/directions (no GOOGLE_MAPS_API_KEY
configured in tests -- see services/maps.py)."""
from app.services import maps


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_geocode_known_city_falls_back_to_gazetteer():
    result = maps.geocode("Delhi")
    assert result is not None
    assert result["demo"] is True
    assert round(result["lat"], 1) == 28.6


def test_geocode_case_insensitive():
    assert maps.geocode("DELHI") is not None
    assert maps.geocode("  Agra  ") is not None


def test_geocode_unknown_place_returns_none():
    assert maps.geocode("Nowhereville Xyzzy") is None


def test_geocode_empty_string_returns_none():
    assert maps.geocode("") is None


def test_directions_demo_mode_uses_haversine_estimate():
    # Delhi -> Agra, roughly 180km apart in reality
    result = maps.directions(28.6139, 77.2090, 27.1767, 78.0081)
    assert result["demo"] is True
    assert 150 < result["distance_km"] < 220
    assert result["duration_min"] > 0
    # No real Directions API call was made -- no turn-by-turn steps to offer.
    assert result["steps"] is None


def test_nominatim_geocode_caches_successful_lookups(monkeypatch):
    # Direct unit test of the private helper (bypasses the is_test gate on
    # geocode() itself) -- verifies the second identical lookup is served
    # from the in-process cache rather than hitting the network again, and
    # that the self-imposed rate floor doesn't actually sleep in tests.
    maps._nominatim_cache.clear()
    monkeypatch.setattr(maps, "_last_nominatim_call", 0.0)
    monkeypatch.setattr(maps.time, "sleep", lambda s: None)

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params["q"])
        return _FakeResponse([{"lat": "26.1664", "lon": "91.7050"}])

    monkeypatch.setattr(maps.httpx, "get", fake_get)

    first = maps._geocode_nominatim("Kamakhya Temple")
    second = maps._geocode_nominatim("kamakhya temple")  # case-insensitive cache key
    assert first == {"lat": 26.1664, "lng": 91.705, "demo": False}
    assert second == first
    assert calls == ["Kamakhya Temple"]  # only one real request made


def test_nominatim_geocode_does_not_cache_failures(monkeypatch):
    maps._nominatim_cache.clear()
    monkeypatch.setattr(maps, "_last_nominatim_call", 0.0)
    monkeypatch.setattr(maps.time, "sleep", lambda s: None)

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params["q"])
        return _FakeResponse([])  # no results -- a genuine miss

    monkeypatch.setattr(maps.httpx, "get", fake_get)

    assert maps._geocode_nominatim("Nowhereville Xyzzy") is None
    assert maps._geocode_nominatim("Nowhereville Xyzzy") is None
    assert len(calls) == 2  # retried, not frozen into a cached failure
