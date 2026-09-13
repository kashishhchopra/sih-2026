"""Currency conversion (services/currency.py + api/currency.py). Mocks the
live rates fetch -- same pattern as test_weather.py -- so tests never
depend on real network access."""
import httpx

from app.services import currency


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _reset_cache():
    currency._cache["rates"] = None
    currency._cache["expires_at"] = 0.0


def test_convert_uses_live_rate(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        currency.httpx, "get",
        lambda *a, **k: FakeResponse({"rates": {"USD": 0.012, "EUR": 0.011}}),
    )
    result = currency.convert_from_inr(1000, "usd")
    assert result["demo"] is False
    assert result["currency"] == "USD"
    assert result["converted"] == 12.0


def test_convert_unknown_currency_is_honest(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        currency.httpx, "get",
        lambda *a, **k: FakeResponse({"rates": {"USD": 0.012}}),
    )
    result = currency.convert_from_inr(1000, "zzz")
    assert result["demo"] is True
    assert result["converted"] is None


def test_convert_falls_back_honestly_on_network_failure(monkeypatch):
    _reset_cache()

    def _raise(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(currency.httpx, "get", _raise)
    result = currency.convert_from_inr(1000, "usd")
    assert result["demo"] is True
    assert result["converted"] is None


def test_convert_api_requires_auth(client):
    r = client.get("/api/currency/convert", params={"amount": 100, "to": "usd"})
    assert r.status_code == 401


def test_convert_api(client, tourist_headers, monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        currency.httpx, "get",
        lambda *a, **k: FakeResponse({"rates": {"USD": 0.012}}),
    )
    r = client.get("/api/currency/convert", headers=tourist_headers, params={"amount": 500, "to": "usd"})
    assert r.status_code == 200
    assert r.json()["converted"] == 6.0
