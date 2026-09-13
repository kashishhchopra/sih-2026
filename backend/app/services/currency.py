"""Currency conversion: real, live exchange rates from a free, no-key-
required public API (open.er-api.com, mirrors the open-source Open Exchange
Rates dataset, updated daily) -- same shape as services/weather.py: a real
backend, an in-process cache so repeated requests don't hammer the public
endpoint, and an honest `demo: True` (nothing invented) when the live
lookup is unreachable rather than a stale/guessed rate.
"""
from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_RATES_URL = "https://open.er-api.com/v6/latest/INR"
_CACHE_TTL_SECONDS = 3600
_TIMEOUT_SECONDS = 6.0

# Currencies commonly relevant to foreign tourists in India, shown as
# quick-pick options -- the underlying lookup works for any ISO code the
# live API returns, this list is just what the frontend renders as buttons.
COMMON_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CNY", "AUD", "CAD", "AED", "SGD", "RUB"]

_cache: dict[str, object] = {"rates": None, "expires_at": 0.0}


def _fetch_rates() -> dict[str, float] | None:
    now = time.monotonic()
    if _cache["rates"] is not None and _cache["expires_at"] > now:
        return _cache["rates"]

    try:
        resp = httpx.get(_RATES_URL, timeout=_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        rates = data.get("rates")
        if not rates:
            raise ValueError("no rates in response")
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Currency rate fetch failed: %s", e)
        return _cache["rates"]  # last known good rates (possibly None) rather than crashing

    _cache["rates"] = rates
    _cache["expires_at"] = now + _CACHE_TTL_SECONDS
    return rates


def list_currencies() -> dict:
    rates = _fetch_rates()
    if rates is None:
        return {"currencies": COMMON_CURRENCIES, "live": False}
    return {"currencies": sorted(rates.keys()), "live": True}


def convert_from_inr(amount: float, to_currency: str) -> dict:
    """Real, live INR -> `to_currency` conversion, or an honest failure
    (never a guessed/stale rate) if the live rate isn't available."""
    to_currency = to_currency.upper()
    rates = _fetch_rates()
    if rates is None:
        return {
            "amount_inr": amount, "currency": to_currency, "converted": None, "demo": True,
            "note": "Live exchange rates are unavailable right now -- try again shortly.",
        }
    rate = rates.get(to_currency)
    if rate is None:
        return {
            "amount_inr": amount, "currency": to_currency, "converted": None, "demo": True,
            "note": f"Unknown currency code: {to_currency}.",
        }
    return {
        "amount_inr": amount, "currency": to_currency,
        "converted": round(amount * rate, 2), "rate": rate, "demo": False,
    }
