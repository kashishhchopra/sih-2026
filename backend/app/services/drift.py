"""Feature-drift monitoring: is live traffic still shaped like training data?

Compares the live distribution of `speed_kmh` (from recent LocationPing rows)
against the distribution recorded at training time, using the Population
Stability Index (PSI) -- a standard, simple drift metric: bin both
distributions the same way, compare bin proportions.

speed_kmh is the only anomaly-model feature honestly comparable this way: the
other three (dist_from_prev_m, inactivity_min, dist_from_route_m) are
engineered per-ping in monitoring.py but never persisted to LocationPing, so
there is no live distribution to compare them against. Extending this would
mean adding those columns -- noted rather than faked.
"""
from __future__ import annotations

import json
import os

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tourist import LocationPing

# Conventional PSI thresholds from the credit-risk modelling literature this
# metric originates in; used here for the same purpose (has the population
# drifted enough that the model's assumptions may no longer hold).
_PSI_STABLE = 0.1
_PSI_MODERATE = 0.25


def _verdict(psi: float) -> str:
    if psi < _PSI_STABLE:
        return "stable"
    if psi < _PSI_MODERATE:
        return "moderate drift"
    return "significant drift"


def compute_psi(bin_edges: list[float], reference_proportions: list[float],
                live_values: np.ndarray) -> float:
    """PSI = sum((live% - ref%) * ln(live% / ref%)) over matching bins.
    A small epsilon avoids log(0)/div-by-0 for empty bins."""
    eps = 1e-4
    live_counts, _ = np.histogram(live_values, bins=bin_edges)
    live_props = live_counts / max(live_counts.sum(), 1)

    psi = 0.0
    for live_p, ref_p in zip(live_props, reference_proportions, strict=True):
        live_p = max(live_p, eps)
        ref_p = max(ref_p, eps)
        psi += (live_p - ref_p) * np.log(live_p / ref_p)
    return round(float(psi), 4)


def get_drift_report(db: Session, sample_size: int = 500) -> dict:
    """Returns a report for every feature with a saved reference distribution,
    or an explanatory dict if there isn't enough live data yet to compare."""
    path = os.path.join(settings.ML_MODELS_DIR, "reference_distributions.json")
    if not os.path.exists(path):
        return {"available": False,
                "reason": "No reference distribution saved. Run: python -m app.ml.train_all"}

    with open(path, encoding="utf-8") as f:
        references = json.load(f)

    live_speeds = db.execute(
        select(LocationPing.speed_kmh).order_by(LocationPing.timestamp.desc()).limit(sample_size)
    ).scalars().all()

    if len(live_speeds) < 30:
        return {
            "available": False,
            "reason": f"Only {len(live_speeds)} live pings recorded; need at least 30 "
                     "for a meaningful comparison.",
        }

    # Only speed_kmh has a live query wired above; a reference entry for any
    # other feature would need its own query, not this one reused wrongly.
    live_by_feature = {"speed_kmh": np.array(live_speeds, dtype=float)}

    features = []
    for name, ref in references.items():
        live_values = live_by_feature.get(name)
        if live_values is None:
            continue
        psi = compute_psi(ref["bin_edges"], ref["proportions"], live_values)
        features.append({
            "feature": name,
            "psi": psi,
            "verdict": _verdict(psi),
            "n_reference": ref["n_samples"],
            "n_live": len(live_values),
        })

    return {"available": True, "features": features}
