"""DBSCAN clustering over historical incident points to auto-discover hot-zones.

Each dense cluster becomes a convex-hull polygon saved as an auto risk zone
definition (JSON), consumed by the seed script to create high-risk Zone rows.
"""
from __future__ import annotations

import json
import os

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics import silhouette_score

from app.ml import registry
from app.ml.generate_data import generate_incident_points


def _convex_hull(points: np.ndarray) -> list[list[float]]:
    """Return hull vertices as [[lat,lng],...]. Falls back to a bbox for tiny sets."""
    try:
        from scipy.spatial import ConvexHull

        hull = ConvexHull(points)
        return [[float(points[v][0]), float(points[v][1])] for v in hull.vertices]
    except Exception:
        lat_min, lng_min = points.min(axis=0)
        lat_max, lng_max = points.max(axis=0)
        return [
            [float(lat_min), float(lng_min)],
            [float(lat_min), float(lng_max)],
            [float(lat_max), float(lng_max)],
            [float(lat_max), float(lng_min)],
        ]


def train(models_dir: str = "ml_models") -> dict:
    os.makedirs(models_dir, exist_ok=True)
    df = generate_incident_points()
    X = df[["lat", "lng"]].values

    # eps in degrees (~0.005 deg ≈ 0.55 km); min_samples requires density
    db = DBSCAN(eps=0.005, min_samples=12).fit(X)
    labels = db.labels_
    unique = sorted(set(labels) - {-1})

    clusters = []
    for lbl in unique:
        pts = X[labels == lbl]
        centroid = pts.mean(axis=0)
        clusters.append({
            "cluster": int(lbl),
            "size": int(len(pts)),
            "centroid": [float(centroid[0]), float(centroid[1])],
            "polygon": _convex_hull(pts),
        })

    n_noise = int((labels == -1).sum())
    sil = None
    core_mask = labels != -1
    if len(unique) > 1 and core_mask.sum() > len(unique):
        sil = round(float(silhouette_score(X[core_mask], labels[core_mask])), 4)

    out_path = os.path.join(models_dir, "hotzones.json")
    with open(out_path, "w") as f:
        json.dump({"clusters": clusters}, f, indent=2)

    metrics = {
        "model": "DBSCAN",
        "task": "high-risk zone discovery (spatial clustering)",
        "eps_deg": 0.005,
        "min_samples": 12,
        "n_points": int(len(X)),
        "n_clusters": len(unique),
        "n_noise": n_noise,
        "silhouette": sil,
        "hotzones_file": out_path,
    }
    version_record = registry.record_version(
        models_dir, "zones", registry.dataset_hash(df), metrics,
        active_files=["hotzones.json"],
    )
    metrics["version"] = version_record["version"]

    print("=== DBSCAN hot-zone clustering ===")
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    train()
