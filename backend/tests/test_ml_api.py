"""Model-evaluation endpoints."""
import json
import os

import pytest


def test_metrics_requires_admin(client, tourist_headers):
    assert client.get("/api/ml/metrics", headers=tourist_headers).status_code == 403


def test_metrics_reports_every_model(client, admin_headers):
    r = client.get("/api/ml/metrics", headers=admin_headers)
    if r.status_code == 404:
        pytest.skip("metrics.json absent; run python -m app.ml.train_all")

    body = r.json()
    assert set(body["models"]) == {"anomaly", "safety", "zones"}
    assert body["training_data"]["source"] == "synthetic"
    assert body["trained_at"]


def test_metrics_include_evaluation_evidence(client, admin_headers):
    r = client.get("/api/ml/metrics", headers=admin_headers)
    if r.status_code == 404:
        pytest.skip("metrics.json absent")

    anomaly = r.json()["models"]["anomaly"]
    for key in ["precision", "recall", "f1", "roc_auc"]:
        assert 0.0 <= anomaly[key] <= 1.0

    cm = anomaly["confusion_matrix"]
    assert set(cm) == {"true_negative", "false_positive",
                       "false_negative", "true_positive"}
    assert all(isinstance(v, int) for v in cm.values())
    assert len(anomaly["roc_curve"]) > 1

    safety = r.json()["models"]["safety"]
    assert safety["r2"] <= 1.0
    assert sum(safety["feature_importances"].values()) == pytest.approx(1.0, abs=0.01)


def test_missing_metrics_file_returns_actionable_404(client, admin_headers, monkeypatch):
    import app.api.ml as ml_api
    monkeypatch.setattr(ml_api, "_metrics_path", lambda: "does/not/exist.json")

    r = client.get("/api/ml/metrics", headers=admin_headers)
    assert r.status_code == 404
    assert "train_all" in r.json()["detail"]


def test_status_reports_inference_mode(client, admin_headers):
    body = client.get("/api/ml/status", headers=admin_headers).json()
    assert body["inference_mode"] in {"model", "rule-based fallback"}
    assert body["live_pings_collected"] == 0
    assert set(body["artifacts"]) == {
        "anomaly_isoforest.joblib", "anomaly_scaler.joblib", "safety_rf.joblib",
    }


def test_status_counts_live_pings(client, admin_headers, db):
    from app.services.monitoring import process_ping
    from tests.conftest import make_tourist

    t = make_tourist(db, itinerary=[])
    process_ping(db, t, 26.14, 91.73, speed_kmh=5)

    assert client.get("/api/ml/status",
                      headers=admin_headers).json()["live_pings_collected"] == 1


def test_feature_contract_matches_the_service(client, admin_headers):
    """The documented contract must match what ml_service actually builds --
    a drift here means training and inference disagree on feature order."""
    from app.services import ml_service

    body = client.get("/api/ml/feature-contract", headers=admin_headers).json()

    assert len(ml_service.anomaly_features(1, 2, 60, 4)) == len(body["anomaly"]["features"])
    assert len(ml_service.safety_features(1, 2, 0.3, 4, 5)) == len(body["safety"]["features"])
    assert body["thresholds"]["route_deviation_m"] > 0
