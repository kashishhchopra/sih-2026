"""Synthetic data generators for training the ML models.

Everything is reproducible (fixed seed) so the academic evaluation metrics are
stable across runs. Three datasets are produced:

  1. Movement/anomaly dataset  -> IsolationForest (unsupervised, with labels for eval)
  2. Safety-score dataset       -> RandomForest regression
  3. Historical incident points -> DBSCAN hot-zone clustering
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

# Guwahati / North-East India demo bounding box (project is India-themed)
CENTER_LAT, CENTER_LNG = 26.1445, 91.7362


def _synthetic_csv(name: str) -> pd.DataFrame | None:
    """Load `<SYNTHETIC_DATA_DIR>/<name>.csv` if the env var is set and the
    file exists, else None. This is the drop-in path documented in
    data/README.md: point SYNTHETIC_DATA_DIR at a corpus written by
    app.scripts.generate_synthetic_dataset and every trainer below uses it
    instead of its parametric generator. Unset (the default), nothing changes
    -- a fresh clone and `docker build` still train with no data files present.
    """
    data_dir = os.environ.get("SYNTHETIC_DATA_DIR")
    if not data_dir:
        return None
    path = os.path.join(data_dir, f"{name}.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def generate_movement_data(n_normal: int = 4000, n_anomaly: int = 400) -> pd.DataFrame:
    """Rows: speed_kmh, dist_from_prev_m, inactivity_min, dist_from_route_m, label.

    label: 0 = normal, 1 = anomaly. Anomalies model the three target scenarios:
      - sudden location drop-off / jump  (huge dist_from_prev)
      - prolonged inactivity              (huge inactivity_min)
      - unusual speed (vehicle abduction) (huge speed)
    """
    real = _synthetic_csv("ml_movement")
    if real is not None:
        cols = ["speed_kmh", "dist_from_prev_m", "inactivity_min", "dist_from_route_m", "label"]
        return real[cols].reset_index(drop=True)
    # Normal walking/short-drive behaviour. A small fraction are "borderline"
    # (fast cabs, brief rests, long sightseeing loops) so the classes overlap and
    # the evaluation metrics stay realistic rather than perfectly separable.
    speed = RNG.normal(10, 12, n_normal).clip(0, 95)
    dist_prev = RNG.normal(200, 400, n_normal).clip(0, 2800)
    inactivity = RNG.normal(5, 8, n_normal).clip(0, 40)
    dist_route = RNG.normal(400, 500, n_normal).clip(0, 2600)
    normal = np.column_stack([speed, dist_prev, inactivity, dist_route])
    normal_labels = np.zeros(n_normal)

    # Anomalies: mix of the three scenarios
    a = n_anomaly // 3
    b = n_anomaly // 3
    c = n_anomaly - a - b

    # scenario 1: sudden jump
    s1 = np.column_stack([
        RNG.normal(30, 10, a).clip(0, 90),
        RNG.normal(8000, 3000, a).clip(3000, 20000),
        RNG.normal(4, 2, a).clip(0, 15),
        RNG.normal(4000, 1500, a).clip(1000, 12000),
    ])
    # scenario 2: prolonged inactivity
    s2 = np.column_stack([
        RNG.normal(0.5, 0.5, b).clip(0, 3),
        RNG.normal(20, 15, b).clip(0, 80),
        RNG.normal(70, 20, b).clip(45, 180),
        RNG.normal(500, 300, b).clip(0, 2000),
    ])
    # scenario 3: unusual high speed (abduction)
    s3 = np.column_stack([
        RNG.normal(150, 30, c).clip(120, 260),
        RNG.normal(5000, 2000, c).clip(2000, 12000),
        RNG.normal(2, 1, c).clip(0, 8),
        RNG.normal(3000, 1500, c).clip(500, 9000),
    ])
    anomaly = np.vstack([s1, s2, s3])
    anomaly_labels = np.ones(n_anomaly)

    X = np.vstack([normal, anomaly])
    y = np.concatenate([normal_labels, anomaly_labels])
    df = pd.DataFrame(
        X, columns=["speed_kmh", "dist_from_prev_m", "inactivity_min", "dist_from_route_m"]
    )
    df["label"] = y
    return df.sample(frac=1, random_state=42).reset_index(drop=True)


def _ncrb_calibrated_crime_index(n: int) -> np.ndarray:
    """Sample crime_index the way it's actually assigned in this app: a zone
    takes one of four real-NCRB-anchored values (see
    app/services/crime_index.py), not a continuous uniform draw that no real
    zone could ever have. Tier frequencies are weighted toward low/medium --
    most of a map is not a restricted zone -- plus a little Gaussian noise so
    the feature isn't perfectly four-valued (a model trained on exactly 4
    unique inputs would generalise poorly)."""
    from app.services.crime_index import calibrate_zone_crime_index

    tiers = ["low", "medium", "high", "restricted"]
    tier_values = np.array([calibrate_zone_crime_index(t) for t in tiers])
    tier_weights = [0.45, 0.30, 0.18, 0.07]
    chosen = RNG.choice(len(tiers), size=n, p=tier_weights)
    noise = RNG.normal(0, 3, n)
    return np.clip(tier_values[chosen] + noise, 0, 100)


def generate_safety_data(n: int = 6000, crime_index_source: str = "uniform") -> pd.DataFrame:
    """Rows: zone_risk, hour, anomaly_score, crime_index, weather_risk, safety_score.

    The target safety_score (0-100, higher=safer) is a weighted risk formula plus
    noise; the RandomForest learns to reproduce it and generalise. This mirrors the
    'weighted model' brief while giving a trainable ML target.

    `crime_index_source`:
      - "uniform" (default): the original RNG.uniform(0,100) draw. Kept as the
        default so existing registry runs stay reproducible/comparable.
      - "ncrb": crime_index drawn from the real NCRB-calibrated tier values
        instead -- see _ncrb_calibrated_crime_index. Train with this via
        `python -m app.ml.train_all --crime-index-source ncrb` to get a
        second, real-data-grounded model version in the registry.
    """
    real = _synthetic_csv("ml_safety")
    if real is not None:
        cols = ["zone_risk", "hour", "anomaly_score", "crime_index", "weather_risk", "safety_score"]
        return real[cols].reset_index(drop=True)

    zone_risk = RNG.uniform(0, 100, n)
    hour = RNG.integers(0, 24, n)
    anomaly_score = RNG.uniform(0, 1, n)
    crime_index = (
        _ncrb_calibrated_crime_index(n) if crime_index_source == "ncrb"
        else RNG.uniform(0, 100, n)
    )
    weather_risk = RNG.uniform(0, 100, n)

    night = ((hour >= 22) | (hour <= 5)).astype(float)
    risk = (
        0.30 * zone_risk
        + 0.25 * anomaly_score * 100
        + 0.25 * crime_index
        + 0.10 * weather_risk
        + 0.10 * (night * 100 + (1 - night) * 20)
    )
    noise = RNG.normal(0, 4, n)
    safety = (100 - risk + noise).clip(0, 100)

    df = pd.DataFrame({
        "zone_risk": zone_risk,
        "hour": hour,
        "anomaly_score": anomaly_score,
        "crime_index": crime_index,
        "weather_risk": weather_risk,
        "safety_score": safety,
    })
    return df


def generate_incident_points(n: int = 800) -> pd.DataFrame:
    """Historical incident lat/lng points clustered around a few hotspots + noise.

    DBSCAN recovers the dense hotspots and labels sparse points as noise; the dense
    clusters become auto-discovered high-risk zones.
    """
    real = _synthetic_csv("ml_incident_points")
    if real is not None:
        return real[["lat", "lng"]].reset_index(drop=True)

    hotspots = [
        (26.1650, 91.7500),
        (26.1250, 91.7150),
        (26.1800, 91.7700),
        (26.1150, 91.7600),
    ]
    points = []
    per = n // (len(hotspots) + 1)
    for lat, lng in hotspots:
        points.append(np.column_stack([
            RNG.normal(lat, 0.0022, per),
            RNG.normal(lng, 0.0022, per),
        ]))
    # scattered noise incidents (sparser so they don't bridge hotspots)
    noise_n = per // 2
    points.append(np.column_stack([
        RNG.uniform(26.10, 26.20, noise_n),
        RNG.uniform(91.70, 91.78, noise_n),
    ]))
    arr = np.vstack(points)
    return pd.DataFrame(arr, columns=["lat", "lng"])


if __name__ == "__main__":
    print(generate_movement_data().head())
    print(generate_safety_data().head())
    print(generate_incident_points().head())
