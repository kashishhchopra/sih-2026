"""Dynamic risk forecast: project a tourist's safety score forward in time.

Combines `trajectory.predict_trajectory` (where they'll likely be) with
`safety.score_at` (how risky that point/hour is) so the dashboard/app can
show "your risk in 15/30/60 minutes", not just right now.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.time import local_hour_for
from app.models.tourist import LocationPing, Tourist
from app.services import trajectory
from app.services.safety import score_at

DEFAULT_HORIZONS_MIN: tuple[int, ...] = (15, 30, 60)


def forecast_risk(
    db: Session, tourist: Tourist, horizons: tuple[int, ...] = DEFAULT_HORIZONS_MIN
) -> list[dict]:
    """Return [{"minutes", "score", "band", "zone"}, ...] for each horizon.

    Each horizon is scored independently against the trajectory predicted for
    that many minutes out, at the anomaly score of the tourist's most recent
    ping (or the same 0.1 default `compute_safety_score` uses when there is
    none). The tourist's own row is never mutated -- `score_at` is a pure
    read against a hypothetical point/hour.
    """
    pings = (
        db.query(LocationPing)
        .filter(LocationPing.tourist_id == tourist.id)
        .order_by(LocationPing.timestamp.desc())
        .limit(5)
        .all()
    )
    pings = list(reversed(pings))  # oldest-first, matching predict_trajectory's expectation
    last = pings[-1] if pings else None
    anomaly_score = last.anomaly_score if last and last.anomaly_score is not None else 0.1

    base_lat = tourist.last_lat if tourist.last_lat is not None else 0.0
    base_lng = tourist.last_lng if tourist.last_lng is not None else 0.0

    max_horizon = max(horizons) if horizons else 0
    predicted = trajectory.predict_trajectory(pings, max_horizon) if pings else []
    by_eta = {round(p[2]): p for p in predicted}

    now_hour = local_hour_for(base_lat, base_lng)
    results = []
    for minutes in horizons:
        point = by_eta.get(minutes)
        if point is not None:
            lat, lng, _eta = point
        else:
            # No usable trajectory (stationary/insufficient history): forecast
            # at the tourist's current position rather than dropping the horizon.
            lat, lng = base_lat, base_lng
        # Approximate future local hour by walking the clock forward with the
        # forecast horizon -- good enough for a night-penalty style feature.
        hour = (now_hour + round(minutes / 60)) % 24
        result = score_at(db, lat, lng, hour, anomaly_score=anomaly_score)
        results.append({
            "minutes": minutes,
            "score": result["score"],
            "band": result["band"],
            "zone": result["breakdown"]["zone"],
        })
    return results
