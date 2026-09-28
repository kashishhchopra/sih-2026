"""Model version registry and drift monitoring."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from app.ml import registry
from app.services import drift


@pytest.fixture
def models_dir(tmp_path):
    d = tmp_path / "ml_models"
    d.mkdir()
    return str(d)


def _write_artifact(models_dir: str, name: str, content: str = "v1") -> None:
    with open(os.path.join(models_dir, name), "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------- registry
def test_dataset_hash_is_deterministic():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    assert registry.dataset_hash(df) == registry.dataset_hash(df.copy())


def test_dataset_hash_differs_for_different_data():
    a = pd.DataFrame({"a": [1, 2, 3]})
    b = pd.DataFrame({"a": [1, 2, 4]})
    assert registry.dataset_hash(a) != registry.dataset_hash(b)


def test_record_version_starts_at_one(models_dir):
    _write_artifact(models_dir, "model.joblib")
    record = registry.record_version(models_dir, "anomaly", "hash1", {"f1": 0.9},
                                     active_files=["model.joblib"])
    assert record["version"] == 1
    assert record["dataset_hash"] == "hash1"
    assert record["metrics_summary"] == {"f1": 0.9}


def test_record_version_increments(models_dir):
    _write_artifact(models_dir, "model.joblib")
    registry.record_version(models_dir, "anomaly", "hash1", {}, active_files=["model.joblib"])
    second = registry.record_version(models_dir, "anomaly", "hash2", {},
                                     active_files=["model.joblib"])
    assert second["version"] == 2

    reg = registry.load_registry(models_dir)
    assert reg["anomaly"]["active_version"] == 2
    assert len(reg["anomaly"]["versions"]) == 2


def test_record_version_copies_versioned_artifacts(models_dir):
    _write_artifact(models_dir, "model.joblib", "the real content")
    registry.record_version(models_dir, "anomaly", "hash1", {}, active_files=["model.joblib"])

    versioned = os.path.join(models_dir, "model_v1.joblib")
    assert os.path.exists(versioned)
    with open(versioned) as f:
        assert f.read() == "the real content"


def test_different_models_tracked_independently(models_dir):
    _write_artifact(models_dir, "a.joblib")
    _write_artifact(models_dir, "b.joblib")
    registry.record_version(models_dir, "anomaly", "h1", {}, active_files=["a.joblib"])
    registry.record_version(models_dir, "safety", "h2", {}, active_files=["b.joblib"])

    reg = registry.load_registry(models_dir)
    assert reg["anomaly"]["active_version"] == 1
    assert reg["safety"]["active_version"] == 1


def test_load_registry_on_missing_file_returns_empty_dict(models_dir):
    assert registry.load_registry(models_dir) == {}


def test_rollback_restores_the_versioned_artifact(models_dir):
    _write_artifact(models_dir, "model.joblib", "version one content")
    registry.record_version(models_dir, "anomaly", "h1", {}, active_files=["model.joblib"])

    _write_artifact(models_dir, "model.joblib", "version two content")
    registry.record_version(models_dir, "anomaly", "h2", {}, active_files=["model.joblib"])

    registry.rollback(models_dir, "anomaly", 1)
    with open(os.path.join(models_dir, "model.joblib")) as f:
        assert f.read() == "version one content"

    reg = registry.load_registry(models_dir)
    assert reg["anomaly"]["active_version"] == 1


def test_rollback_to_unknown_version_raises(models_dir):
    _write_artifact(models_dir, "model.joblib")
    registry.record_version(models_dir, "anomaly", "h1", {}, active_files=["model.joblib"])
    with pytest.raises(ValueError, match="version 99"):
        registry.rollback(models_dir, "anomaly", 99)


def test_save_reference_distribution_writes_bins_and_proportions(models_dir):
    values = np.concatenate([np.full(50, 5.0), np.full(50, 20.0)])
    registry.save_reference_distribution(models_dir, "speed_kmh", values, n_bins=4)

    with open(os.path.join(models_dir, "reference_distributions.json")) as f:
        saved = json.load(f)
    assert saved["speed_kmh"]["n_samples"] == 100
    assert abs(sum(saved["speed_kmh"]["proportions"]) - 1.0) < 1e-6


def test_save_reference_distribution_skips_a_constant_feature(models_dir):
    """A feature with zero variance has no meaningful bins -- must not crash
    or write a degenerate single-edge entry."""
    registry.save_reference_distribution(models_dir, "constant", np.full(50, 7.0))
    path = os.path.join(models_dir, "reference_distributions.json")
    if os.path.exists(path):
        with open(path) as f:
            assert "constant" not in json.load(f)


def test_save_reference_distribution_accumulates_multiple_features(models_dir):
    registry.save_reference_distribution(models_dir, "speed_kmh", np.random.default_rng(1).normal(10, 3, 200))
    registry.save_reference_distribution(models_dir, "other", np.random.default_rng(2).normal(50, 5, 200))
    with open(os.path.join(models_dir, "reference_distributions.json")) as f:
        saved = json.load(f)
    assert set(saved) == {"speed_kmh", "other"}


# ---------------------------------------------------------------- drift / PSI
def test_psi_is_near_zero_for_identical_distributions():
    rng = np.random.default_rng(7)
    values = rng.normal(10, 3, 2000)
    edges = np.unique(np.quantile(values, np.linspace(0, 1, 11)))
    counts, _ = np.histogram(values, bins=edges)
    proportions = (counts / counts.sum()).tolist()

    psi = drift.compute_psi(edges.tolist(), proportions, values)
    assert psi < 0.01


def test_psi_is_large_for_a_completely_different_distribution():
    rng = np.random.default_rng(7)
    reference = rng.normal(10, 3, 2000)
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, 11)))
    counts, _ = np.histogram(reference, bins=edges)
    proportions = (counts / counts.sum()).tolist()

    shifted = rng.normal(200, 3, 200)  # nowhere near the reference range
    psi = drift.compute_psi(edges.tolist(), proportions, shifted)
    assert psi > 1.0


@pytest.mark.parametrize("psi,expected", [
    (0.02, "stable"), (0.09, "stable"),
    (0.15, "moderate drift"), (0.24, "moderate drift"),
    (0.3, "significant drift"), (5.0, "significant drift"),
])
def test_verdict_thresholds(psi, expected):
    assert drift._verdict(psi) == expected


def test_drift_report_unavailable_with_no_reference_file(db, monkeypatch):
    monkeypatch.setattr("app.services.drift.settings.ML_MODELS_DIR", "/does/not/exist")
    report = drift.get_drift_report(db)
    assert report["available"] is False
    assert "train_all" in report["reason"]


def test_drift_report_unavailable_with_too_few_live_pings(db, models_dir, monkeypatch):
    registry.save_reference_distribution(models_dir, "speed_kmh", np.random.default_rng(1).normal(10, 3, 200))
    monkeypatch.setattr("app.services.drift.settings.ML_MODELS_DIR", models_dir)

    from app.services.monitoring import process_ping
    from tests.conftest import make_tourist
    t = make_tourist(db, itinerary=[])
    for _ in range(5):  # fewer than the 30-ping minimum
        process_ping(db, t, 26.14, 91.73, speed_kmh=5)

    report = drift.get_drift_report(db)
    assert report["available"] is False
    assert "30" in report["reason"]


def test_drift_report_computes_psi_once_enough_pings_exist(db, models_dir, monkeypatch):
    rng = np.random.default_rng(3)
    registry.save_reference_distribution(models_dir, "speed_kmh", rng.normal(10, 3, 500))
    monkeypatch.setattr("app.services.drift.settings.ML_MODELS_DIR", models_dir)

    from app.services.monitoring import process_ping
    from tests.conftest import make_tourist
    t = make_tourist(db, itinerary=[])
    for s in rng.normal(10, 3, 40):
        process_ping(db, t, 26.14, 91.73, speed_kmh=max(0, float(s)))

    report = drift.get_drift_report(db)
    assert report["available"] is True
    feature = report["features"][0]
    assert feature["feature"] == "speed_kmh"
    assert feature["n_live"] == 40
    assert feature["psi"] >= 0


def test_ml_registry_endpoint(client, admin_headers, monkeypatch, models_dir):
    registry.record_version(models_dir, "anomaly", "h1", {"f1": 0.9}, active_files=[])
    monkeypatch.setattr("app.api.ml.settings.ML_MODELS_DIR", models_dir)

    r = client.get("/api/ml/registry", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["anomaly"]["active_version"] == 1


def test_ml_registry_endpoint_404_when_empty(client, admin_headers, monkeypatch, models_dir):
    monkeypatch.setattr("app.api.ml.settings.ML_MODELS_DIR", models_dir)
    assert client.get("/api/ml/registry", headers=admin_headers).status_code == 404


def test_ml_drift_endpoint_requires_admin(client, tourist_headers):
    assert client.get("/api/ml/drift", headers=tourist_headers).status_code == 403


def test_ml_registry_endpoint_requires_admin(client, tourist_headers):
    assert client.get("/api/ml/registry", headers=tourist_headers).status_code == 403
