"""Loads trained ML artifacts (joblib) and serves inference to the API.

Models are lazily loaded and cached. If a model file is missing (e.g. training
hasn't been run yet) the service degrades gracefully to rule-based fallbacks so
the API never crashes during a demo.
"""
from __future__ import annotations

import os
import threading
from typing import Any

import numpy as np

from app.core.config import settings

_cache: dict[str, Any] = {}
# Guards the *first* load of each artifact. FastAPI runs sync endpoints in a
# threadpool, so under concurrent load several request threads can reach an
# empty `_cache` at once. `joblib.load()` on a first call triggers Python's
# import machinery to pull in sklearn's compiled submodules; several threads
# doing that concurrently for the first time can trip CPython's import lock
# into `_DeadlockError` (observed under locust load-testing this endpoint).
# A plain lock serializes the load -- once cached, later calls hit the dict
# directly and never touch the lock, so steady-state inference is unaffected.
_load_lock = threading.Lock()


def _path(name: str) -> str:
    return os.path.join(settings.ML_MODELS_DIR, name)


def _load(name: str):
    if name not in _cache:
        with _load_lock:
            if name not in _cache:  # re-check: another thread may have won the race
                import joblib

                p = _path(name)
                _cache[name] = joblib.load(p) if os.path.exists(p) else None
    return _cache[name]


# ---------------------------------------------------------------- anomaly (IsolationForest)
def anomaly_features(speed_kmh: float, dist_from_prev_m: float, dt_seconds: float,
                     dist_from_route_m: float) -> list[float]:
    """Feature vector for the anomaly model. Kept in one place so training and
    inference use identical ordering."""
    inactivity_min = dt_seconds / 60.0
    return [speed_kmh, dist_from_prev_m, inactivity_min, dist_from_route_m]


def score_anomaly(features: list[float]) -> dict:
    """Return {is_anomaly, score} where score in [0,1], higher = more anomalous."""
    model = _load("anomaly_isoforest.joblib")
    scaler = _load("anomaly_scaler.joblib")
    if model is None or scaler is None:
        # Rule-based fallback: flag extreme speed or long inactivity
        speed, dist_prev, inactivity_min, dist_route = features
        rule = speed > 120 or inactivity_min > 45 or dist_route > 3000
        return {"is_anomaly": bool(rule), "score": 0.85 if rule else 0.1}

    X = scaler.transform(np.array([features], dtype=float))
    pred = model.predict(X)[0]  # -1 anomaly, 1 normal
    # decision_function: higher = more normal. Convert to 0-1 anomaly score.
    raw = model.decision_function(X)[0]
    score = float(1.0 / (1.0 + np.exp(5 * raw)))  # squash to (0,1)
    return {"is_anomaly": bool(pred == -1), "score": round(score, 3)}


# ---------------------------------------------------------------- safety score (RandomForest)
def safety_features(zone_risk: float, hour: int, anomaly_score: float,
                    crime_index: float, weather_risk: float) -> list[float]:
    return [zone_risk, hour, anomaly_score, crime_index, weather_risk]


def predict_safety_score(features: list[float]) -> float:
    """Predict a 0-100 safety score. Higher = safer."""
    model = _load("safety_rf.joblib")
    if model is None:
        # Weighted fallback identical in spirit to the training target
        zone_risk, hour, anomaly_score, crime_index, weather_risk = features
        risk = (
            0.30 * zone_risk
            + 0.25 * anomaly_score * 100
            + 0.25 * crime_index
            + 0.10 * weather_risk
            + 0.10 * (100 if (hour >= 22 or hour <= 5) else 20)
        )
        return round(max(0.0, min(100.0, 100.0 - risk)), 1)
    pred = float(model.predict(np.array([features], dtype=float))[0])
    return round(max(0.0, min(100.0, pred)), 1)


def clear_cache() -> None:
    _cache.clear()
