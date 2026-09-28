"""Fair Price: estimates a reasonable fare range for local transport (auto-
rickshaw, taxi/cab, bike-taxi) so a tourist can tell whether a quoted price
is reasonable before paying.

Real distance/duration from services/maps.py's existing directions()
adapter (routed when GOOGLE_MAPS_API_KEY is set, an honestly-labelled
straight-line estimate otherwise -- reused here, not duplicated). The fare
itself is `base_fare + per_km_rate * distance + per_min_rate * duration`,
using a rate card sourced from Settings (backend/.env.example) rather than a
single number baked into this file -- this is how a city's real RTO-
published auto/taxi tariff card actually works (a base + per-km/per-min
rate, not one fixed price for every trip), so a deployment can point it at
its own city's real published tariffs via env vars instead of a fabricated
number.
"""
from __future__ import annotations

from app.core.config import settings
from app.services import maps

# transport_type -> (base_fare_inr, per_km_inr, per_min_inr). Defaults are
# broadly representative starting rates for a mid-size Indian city (informed
# by typical auto/taxi tariff structures) -- NOT a specific city's official
# tariff. A real deployment should override these via env vars with the
# actual RTO/state-published tariff for wherever it operates.
RATE_CARD: dict[str, tuple[float, float, float]] = {
    "auto_rickshaw": (
        settings.FARE_AUTO_BASE, settings.FARE_AUTO_PER_KM, settings.FARE_AUTO_PER_MIN,
    ),
    "taxi": (
        settings.FARE_TAXI_BASE, settings.FARE_TAXI_PER_KM, settings.FARE_TAXI_PER_MIN,
    ),
    "cab": (
        settings.FARE_CAB_BASE, settings.FARE_CAB_PER_KM, settings.FARE_CAB_PER_MIN,
    ),
    "bike_taxi": (
        settings.FARE_BIKE_BASE, settings.FARE_BIKE_PER_KM, settings.FARE_BIKE_PER_MIN,
    ),
}

TRANSPORT_TYPES = list(RATE_CARD.keys())

# A quoted fare's percent-over-estimate maps to a verdict. Bands, not a
# single cutoff, so "fair" tolerates normal night/surge/traffic variance
# without flagging every reasonable trip as overpriced.
_SLIGHTLY_HIGH_PCT = 15.0
_OVERPRICED_PCT = 40.0
_SUSPICIOUS_PCT = 80.0


def estimate_fare(transport_type: str, distance_km: float, duration_min: float) -> tuple[float, float]:
    """(min, max) reasonable fare in INR for this trip. The range comes from
    applying the rate card at -10%/+15% of the base distance/time rates --
    real trips vary (traffic, waiting, minor detours), so a single point
    estimate would flag normal variance as "overpriced"."""
    base, per_km, per_min = RATE_CARD.get(transport_type, RATE_CARD["auto_rickshaw"])
    point = base + per_km * distance_km + per_min * duration_min
    return round(point * 0.90, 2), round(point * 1.15, 2)


def _verdict(quoted: float, est_min: float, est_max: float) -> tuple[str, float]:
    """Verdict + percent the quoted fare is over the top of the estimated
    range (0 or negative if at/under the range -- never flagged as high)."""
    if quoted <= est_max:
        return "fair", 0.0
    pct_over = round((quoted - est_max) / est_max * 100, 1)
    if pct_over >= _SUSPICIOUS_PCT:
        return "suspicious", pct_over
    if pct_over >= _OVERPRICED_PCT:
        return "overpriced", pct_over
    if pct_over >= _SLIGHTLY_HIGH_PCT:
        return "slightly_high", pct_over
    return "fair", pct_over


def check_fare(
    transport_type: str, pickup_lat: float, pickup_lng: float,
    dest_lat: float, dest_lng: float, quoted_fare: float,
) -> dict:
    """The full Fair Price check: real distance/duration, a transparent
    estimated range, and a verdict on the quoted price -- everything a
    tourist needs to decide whether to pay or push back, with the reasoning
    shown, not just a label."""
    route = maps.directions(pickup_lat, pickup_lng, dest_lat, dest_lng)
    distance_km = route["distance_km"]
    duration_min = route["duration_min"]

    est_min, est_max = estimate_fare(transport_type, distance_km, duration_min)
    verdict, pct_over = _verdict(quoted_fare, est_min, est_max)

    return {
        "transport_type": transport_type,
        "distance_km": distance_km, "duration_min": duration_min,
        "route_demo": route["demo"],  # honest: straight-line estimate vs a real routed distance
        "estimated_min": est_min, "estimated_max": est_max,
        "quoted_fare": quoted_fare, "verdict": verdict, "percent_over": pct_over,
    }
