"""ML inference wrapper, including the rule-based fallbacks.

The fallbacks matter: if the joblib artifacts are missing (a fresh clone before
`train_all` has run) the API must still answer rather than 500 during a demo.
"""
import pytest

from app.services import ml_service


@pytest.fixture
def no_models(monkeypatch):
    """Force every model lookup to miss, exercising the fallback paths."""
    monkeypatch.setattr(ml_service, "_load", lambda name: None)


def test_anomaly_feature_order_is_stable():
    feats = ml_service.anomaly_features(speed_kmh=50, dist_from_prev_m=100,
                                        dt_seconds=120, dist_from_route_m=800)
    assert feats == [50, 100, 2.0, 800]  # dt converted to minutes


def test_fallback_flags_extreme_speed(no_models):
    feats = ml_service.anomaly_features(150, 5000, 60, 500)
    assert ml_service.score_anomaly(feats)["is_anomaly"] is True


def test_fallback_flags_prolonged_inactivity(no_models):
    feats = ml_service.anomaly_features(0.2, 10, 60 * 60, 200)  # 60 minutes
    assert ml_service.score_anomaly(feats)["is_anomaly"] is True


def test_fallback_flags_route_deviation(no_models):
    feats = ml_service.anomaly_features(5, 100, 60, 5000)
    assert ml_service.score_anomaly(feats)["is_anomaly"] is True


def test_fallback_accepts_normal_movement(no_models):
    feats = ml_service.anomaly_features(5, 120, 60, 300)
    assert ml_service.score_anomaly(feats)["is_anomaly"] is False


def test_anomaly_score_always_in_unit_range():
    for feats in [[0, 0, 0, 0], [200, 20000, 300, 15000], [5, 100, 1, 200]]:
        assert 0.0 <= ml_service.score_anomaly(feats)["score"] <= 1.0


@pytest.mark.parametrize("zone_risk,crime,expected_order", [
    (100.0, 100.0, "low"),
    (0.0, 0.0, "high"),
])
def test_safety_score_responds_to_risk(no_models, zone_risk, crime, expected_order):
    score = ml_service.predict_safety_score(
        ml_service.safety_features(zone_risk, 12, 0.1, crime, 10.0)
    )
    assert (score < 50) if expected_order == "low" else (score > 50)


def test_safety_score_is_clamped_to_0_100(no_models):
    extremes = [
        ml_service.safety_features(100, 3, 1.0, 100, 100),   # worst case
        ml_service.safety_features(0, 12, 0.0, 0, 0),        # best case
    ]
    for feats in extremes:
        assert 0.0 <= ml_service.predict_safety_score(feats) <= 100.0


def test_night_hours_reduce_the_score(no_models):
    day = ml_service.predict_safety_score(ml_service.safety_features(20, 13, 0.1, 20, 10))
    night = ml_service.predict_safety_score(ml_service.safety_features(20, 2, 0.1, 20, 10))
    assert night < day


def test_concurrent_first_load_is_thread_safe(tmp_path, monkeypatch):
    """Regression test for a real deadlock found under load-testing: many
    threads racing to load an artifact for the first time must not corrupt
    the cache or crash -- they should all end up with the same loaded object."""
    import threading

    import joblib

    monkeypatch.setattr(ml_service, "_cache", {})
    model_path = tmp_path / "fake_model.joblib"
    joblib.dump({"marker": "loaded"}, model_path)
    monkeypatch.setattr(ml_service.settings, "ML_MODELS_DIR", str(tmp_path))

    results = []
    barrier = threading.Barrier(16)

    def worker():
        barrier.wait()  # maximise the chance every thread hits the race window
        results.append(ml_service._load("fake_model.joblib"))

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(results) == 16
    assert all(r == {"marker": "loaded"} for r in results)
