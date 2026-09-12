"""Model Lab: activating/rolling back a previously trained model version
(POST /ml/registry/{model}/rollback/{version})."""
import pytest

from app.ml import registry
from app.services import ml_service


@pytest.fixture
def models_dir(tmp_path):
    d = tmp_path / "ml_models"
    d.mkdir()
    return str(d)


def _seed_two_versions(models_dir):
    import os
    v1_file = os.path.join(models_dir, "safety_rf.joblib")
    with open(v1_file, "wb") as f:
        f.write(b"v1-bytes")
    registry.record_version(models_dir, "safety", "hash1", {"r2": 0.8},
                            active_files=["safety_rf.joblib"])
    with open(v1_file, "wb") as f:
        f.write(b"v2-bytes")
    registry.record_version(models_dir, "safety", "hash2", {"r2": 0.9},
                            active_files=["safety_rf.joblib"])
    return v1_file


def test_rollback_restores_previous_version_artifact(client, admin_headers, monkeypatch, models_dir):
    active_file = _seed_two_versions(models_dir)
    monkeypatch.setattr("app.api.ml.settings.ML_MODELS_DIR", models_dir)

    r = client.post("/api/ml/registry/safety/rollback/1", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["active_version"] == 1

    with open(active_file, "rb") as f:
        assert f.read() == b"v1-bytes"

    reg = registry.load_registry(models_dir)
    assert reg["safety"]["active_version"] == 1


def test_rollback_clears_ml_service_cache(client, admin_headers, monkeypatch, models_dir):
    _seed_two_versions(models_dir)
    monkeypatch.setattr("app.api.ml.settings.ML_MODELS_DIR", models_dir)
    ml_service._cache["sentinel"] = object()

    client.post("/api/ml/registry/safety/rollback/1", headers=admin_headers)

    assert "sentinel" not in ml_service._cache


def test_rollback_unknown_version_404(client, admin_headers, monkeypatch, models_dir):
    _seed_two_versions(models_dir)
    monkeypatch.setattr("app.api.ml.settings.ML_MODELS_DIR", models_dir)

    r = client.post("/api/ml/registry/safety/rollback/99", headers=admin_headers)
    assert r.status_code == 404


def test_rollback_forbidden_for_responder(client, responder_headers, monkeypatch, models_dir):
    _seed_two_versions(models_dir)
    monkeypatch.setattr("app.api.ml.settings.ML_MODELS_DIR", models_dir)

    r = client.post("/api/ml/registry/safety/rollback/1", headers=responder_headers)
    assert r.status_code == 403
