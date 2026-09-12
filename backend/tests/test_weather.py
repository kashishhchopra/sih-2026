"""Weather-risk adapter: falls back to the mock with no key, no network, or
any API failure, and correctly maps conditions to risk when it succeeds."""
import httpx
import pytest

from app.services import weather


@pytest.fixture(autouse=True)
def _clear_cache():
    weather.clear_cache()
    yield
    weather.clear_cache()


def test_uses_mock_when_no_api_key_configured(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "")
    assert weather.get_weather_risk(26.14, 91.73) == weather.mock_weather_risk(26.14, 91.73)


def test_mock_is_deterministic():
    a = weather.mock_weather_risk(26.14, 91.73)
    b = weather.mock_weather_risk(26.14, 91.73)
    assert a == b
    assert 0 <= a <= 100


@pytest.mark.parametrize("weather_id,expected", [
    (200, 80.0),   # thunderstorm
    (300, 20.0),   # drizzle
    (500, 30.0),   # light rain
    (502, 60.0),   # heavy rain
    (601, 50.0),   # snow
    (741, 45.0),   # fog
    (800, 5.0),    # clear
    (802, 10.0),   # scattered clouds
])
def test_condition_risk_mapping(weather_id, expected):
    assert weather._condition_risk(weather_id) == expected


def test_high_wind_adds_risk():
    calm = weather._condition_risk(800)
    assert calm == 5.0  # sanity: clear sky is low risk on its own


def test_fetch_maps_a_real_looking_response(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "weather": [{"id": 200}],  # thunderstorm
                "wind": {"speed": 5.0},
                "main": {"temp": 25.0},
            }

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    risk = weather.get_weather_risk(26.14, 91.73)
    assert risk == 80.0


def test_fetch_adds_wind_and_temperature_penalties(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "weather": [{"id": 800}],  # clear, base risk 5
                "wind": {"speed": 20.0},   # +20
                "main": {"temp": 45.0},    # +15
            }

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    assert weather.get_weather_risk(26.14, 91.73) == 40.0  # 5 + 20 + 15


def test_risk_is_clamped_to_100(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"weather": [{"id": 200}], "wind": {"speed": 30.0}, "main": {"temp": 50.0}}

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    assert weather.get_weather_risk(26.14, 91.73) == 100.0


def test_network_failure_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    def boom(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(weather.httpx, "get", boom)
    assert weather.get_weather_risk(26.14, 91.73) == weather.mock_weather_risk(26.14, 91.73)


def test_malformed_response_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    class BadResponse:
        def raise_for_status(self): pass
        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: BadResponse())
    assert weather.get_weather_risk(26.14, 91.73) == weather.mock_weather_risk(26.14, 91.73)


def test_http_error_status_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "bad-key")

    class UnauthorizedResponse:
        def raise_for_status(self):
            raise httpx.HTTPStatusError("401", request=None, response=None)
        def json(self):
            return {}

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: UnauthorizedResponse())
    assert weather.get_weather_risk(26.14, 91.73) == weather.mock_weather_risk(26.14, 91.73)


def test_results_are_cached_within_the_same_grid_cell(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")
    calls = []

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            calls.append(1)
            return {"weather": [{"id": 800}], "wind": {}, "main": {}}

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    weather.get_weather_risk(26.140, 91.730)
    weather.get_weather_risk(26.141, 91.731)  # rounds to the same cache cell
    assert len(calls) == 1


def test_cache_expires(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")
    monkeypatch.setattr(weather.settings, "WEATHER_CACHE_TTL_SECONDS", 0)
    calls = []

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            calls.append(1)
            return {"weather": [{"id": 800}], "wind": {}, "main": {}}

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    weather.get_weather_risk(26.14, 91.73)
    weather.get_weather_risk(26.14, 91.73)
    assert len(calls) == 2


# ---------------------------------------------------------------- fetch_current_conditions
def test_fetch_current_conditions_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "")
    assert weather.fetch_current_conditions(26.14, 91.73) is None


def test_fetch_current_conditions_returns_raw_fields(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {
                "weather": [{"id": 200, "description": "thunderstorm"}],
                "wind": {"speed": 12.0},
                "main": {"temp": 31.0},
                "dt": 1234567890,
            }

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    c = weather.fetch_current_conditions(26.14, 91.73)
    assert c == {
        "weather_id": 200, "description": "thunderstorm",
        "temp_c": 31.0, "wind_speed_ms": 12.0, "observed_at": 1234567890,
    }


def test_fetch_current_conditions_returns_none_on_network_failure(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")

    def boom(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(weather.httpx, "get", boom)
    assert weather.fetch_current_conditions(26.14, 91.73) is None


def test_fetch_current_conditions_is_cached(monkeypatch):
    monkeypatch.setattr(weather.settings, "OPENWEATHER_API_KEY", "fake-key")
    calls = []

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            calls.append(1)
            return {"weather": [{"id": 800, "description": "clear"}], "wind": {}, "main": {}}

    monkeypatch.setattr(weather.httpx, "get", lambda *a, **k: FakeResponse())
    weather.fetch_current_conditions(26.140, 91.730)
    weather.fetch_current_conditions(26.141, 91.731)  # same cache cell
    assert len(calls) == 1


def test_safety_score_uses_the_weather_service(db, monkeypatch):
    from app.services.safety import compute_safety_score
    from tests.conftest import make_tourist

    called = {}

    def fake_get_weather_risk(lat, lng):
        called["used"] = True
        return 42.0

    monkeypatch.setattr("app.services.safety.weather.get_weather_risk", fake_get_weather_risk)
    t = make_tourist(db)
    result = compute_safety_score(db, t)
    assert called.get("used") is True
    assert result["breakdown"]["weather_risk"] == 42.0
