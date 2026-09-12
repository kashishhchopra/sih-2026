"""Compute a tourist's dynamic 0-100 safety score with an explainable breakdown."""
import json

from sqlalchemy.orm import Session

from app.core.time import local_hour_for
from app.models.tourist import Tourist
from app.models.zone import Zone
from app.services import explain, ml_service, weather
from app.services.geo import zones_containing_point

_RISK_WEIGHT = {"low": 20.0, "medium": 50.0, "high": 80.0, "restricted": 100.0}


def band_for(score: float) -> str:
    if score >= 75:
        return "safe"
    if score >= 50:
        return "moderate"
    if score >= 25:
        return "risky"
    return "danger"


def zone_time_multiplier(zone: Zone, hour: int) -> float:
    """Hour-of-day multiplier on a zone's base risk weight, from its curve.

    `time_risk_curve` is a JSON object like {"20": 1.3, "6": 0.6} -- hour of
    day (as a string key) -> multiplier. An empty/missing curve, or any
    malformed value, falls back to 1.0 (flat behavior) rather than ever
    raising -- a bad curve must never crash safety scoring.
    """
    raw = getattr(zone, "time_risk_curve", None) or "{}"
    try:
        curve = json.loads(raw)
        if not isinstance(curve, dict):
            return 1.0
        return float(curve.get(str(hour), 1.0))
    except (TypeError, ValueError):
        return 1.0


def score_at(db: Session, lat: float, lng: float, hour: int, anomaly_score: float = 0.1) -> dict:
    """Evaluate the safety-score model at an arbitrary point/hour, independent
    of any particular tourist row. Shared by `compute_safety_score` (the
    tourist's live position) and `app.services.forecast` (predicted future
    positions) so the scoring logic lives in exactly one place."""
    zones = db.query(Zone).all()
    inside = zones_containing_point(lat, lng, zones) if (lat or lng) else []
    if inside:
        worst = max(inside, key=lambda z: _RISK_WEIGHT.get(z.risk_level, 50))
        zone_risk = _RISK_WEIGHT.get(worst.risk_level, 50) * zone_time_multiplier(worst, hour)
        crime_index = worst.crime_index
        zone_name = worst.name
    else:
        zone_risk, crime_index, zone_name = 15.0, 20.0, "open area"

    weather_risk = weather.get_weather_risk(lat, lng)

    feats = ml_service.safety_features(zone_risk, hour, anomaly_score, crime_index, weather_risk)
    score = ml_service.predict_safety_score(feats)

    breakdown = {
        "zone": zone_name,
        "zone_risk": zone_risk,
        "crime_index": crime_index,
        "hour": hour,
        "night_penalty": hour >= 22 or hour <= 5,
        "anomaly_score": round(anomaly_score, 3),
        "weather_risk": weather_risk,
        # Per-feature SHAP contributions for THIS prediction -- None when only
        # the rule-based fallback is active, since that's already an explicit
        # formula with nothing to decompose.
        "explanation": explain.explain_safety_score(feats),
    }
    return {"score": score, "band": band_for(score), "breakdown": breakdown}


def compute_safety_score(
    db: Session, tourist: Tourist, anomaly_score: float = 0.1
) -> dict:
    """Returns {score, band, breakdown}. Uses the RandomForest model when available."""
    lat = tourist.last_lat if tourist.last_lat is not None else 0.0
    lng = tourist.last_lng if tourist.last_lng is not None else 0.0
    hour = local_hour_for(lat, lng)
    return score_at(db, lat, lng, hour, anomaly_score)
