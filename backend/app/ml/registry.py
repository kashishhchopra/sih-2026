"""Model version registry.

`ml_service` always loads a fixed, unversioned filename (e.g.
`anomaly_isoforest.joblib`) -- that stays true here, so serving code never
has to resolve a version on the hot path. What this adds is a history
alongside it: every training run is recorded with its metrics and a hash of
the data it was trained on, and each run's artifacts are also copied under a
versioned filename, so a bad training run can be rolled back to a known-good
version without retraining.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd


def dataset_hash(df: pd.DataFrame) -> str:
    """Deterministic hash of a training dataframe's contents."""
    return hashlib.sha256(
        pd.util.hash_pandas_object(df, index=False).values.tobytes()
    ).hexdigest()[:16]


def _registry_path(models_dir: str) -> str:
    return os.path.join(models_dir, "registry.json")


def load_registry(models_dir: str) -> dict[str, Any]:
    path = _registry_path(models_dir)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_registry(models_dir: str, registry: dict[str, Any]) -> None:
    with open(_registry_path(models_dir), "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)


def record_version(
    models_dir: str, model_name: str, data_hash: str, metrics: dict[str, Any],
    active_files: list[str],
) -> dict[str, Any]:
    """Copy each active artifact under a versioned filename and append a
    registry entry. Returns the new version's record."""
    registry = load_registry(models_dir)
    entry = registry.setdefault(model_name, {"active_version": 0, "versions": []})
    version = entry["active_version"] + 1

    versioned_files = []
    for filename in active_files:
        src = os.path.join(models_dir, filename)
        if not os.path.exists(src):
            continue
        stem, ext = os.path.splitext(filename)
        versioned_name = f"{stem}_v{version}{ext}"
        shutil.copy2(src, os.path.join(models_dir, versioned_name))
        versioned_files.append(versioned_name)

    record = {
        "version": version,
        "trained_at": datetime.now(UTC).isoformat(),
        "dataset_hash": data_hash,
        "metrics_summary": metrics,
        "active_files": active_files,
        "versioned_files": versioned_files,
    }
    entry["versions"].append(record)
    entry["active_version"] = version
    _save_registry(models_dir, registry)
    return record


def rollback(models_dir: str, model_name: str, version: int) -> dict[str, Any]:
    """Restore a previous version's artifacts as the active (unversioned)
    files. Raises ValueError if that version isn't in the registry."""
    registry = load_registry(models_dir)
    entry = registry.get(model_name)
    record = next((v for v in (entry or {}).get("versions", []) if v["version"] == version), None)
    if record is None:
        raise ValueError(f"No recorded version {version} for model '{model_name}'")

    for active_name, versioned_name in zip(
        record["active_files"], record["versioned_files"], strict=True
    ):
        shutil.copy2(
            os.path.join(models_dir, versioned_name),
            os.path.join(models_dir, active_name),
        )

    entry["active_version"] = version
    _save_registry(models_dir, registry)
    return record


def save_reference_distribution(models_dir: str, feature_name: str,
                                values: np.ndarray, n_bins: int = 10) -> None:
    """Persist the training-time distribution of one feature (as decile bin
    edges + expected proportions) for later drift comparison against live
    data. See app/services/drift.py."""
    quantiles = np.linspace(0, 1, n_bins + 1)
    edges = np.unique(np.quantile(values, quantiles))
    if len(edges) < 2:
        return  # degenerate (constant) feature: nothing meaningful to compare
    counts, _ = np.histogram(values, bins=edges)
    proportions = (counts / counts.sum()).tolist()

    path = os.path.join(models_dir, "reference_distributions.json")
    existing = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    existing[feature_name] = {
        "bin_edges": edges.tolist(),
        "proportions": proportions,
        "n_samples": int(len(values)),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
