"""Per-prediction explainability for the safety-score model.

`compute_safety_score`'s `breakdown` already reports the raw feature values
(zone_risk, hour, anomaly_score, crime_index, weather_risk) but not how much
each one actually moved the score. SHAP (TreeExplainer, exact for tree
ensembles) answers that: for one prediction, how many points did each feature
add or subtract relative to the model's average output.

Lazily loaded and cached, same pattern as ml_service._load -- including the
same double-checked lock, since this is reached from the same FastAPI
threadpool and a concurrent first-load race is exactly what caused the
_DeadlockError fixed in ml_service (see git history)."""
from __future__ import annotations

import threading
from typing import Any

import numpy as np

from app.services import ml_service

_explainer_cache: dict[str, Any] = {}
_explainer_lock = threading.Lock()

SAFETY_FEATURE_NAMES = ["zone_risk", "hour", "anomaly_score", "crime_index", "weather_risk"]


def _safety_explainer():
    if "safety" not in _explainer_cache:
        with _explainer_lock:
            if "safety" not in _explainer_cache:
                model = ml_service._load("safety_rf.joblib")
                if model is None:
                    _explainer_cache["safety"] = None
                else:
                    import shap
                    _explainer_cache["safety"] = shap.TreeExplainer(model)
    return _explainer_cache["safety"]


def explain_safety_score(features: list[float]) -> dict[str, Any] | None:
    """Per-feature SHAP contributions for one safety-score prediction, or
    None if no trained model is loaded (the rule-based fallback has no
    meaningful SHAP decomposition -- it's an explicit formula already)."""
    explainer = _safety_explainer()
    if explainer is None:
        return None

    X = np.array([features], dtype=float)
    shap_values = explainer.shap_values(X)[0]
    return {
        "base_value": round(float(np.ravel(explainer.expected_value)[0]), 2),
        "contributions": {
            name: round(float(value), 2)
            for name, value in zip(SAFETY_FEATURE_NAMES, shap_values, strict=True)
        },
    }


def clear_cache() -> None:
    _explainer_cache.clear()
