"""SHAP explainability for the safety-score model."""
import pytest

from app.services import explain, ml_service


@pytest.fixture(autouse=True)
def _clear_explainer_cache():
    explain.clear_cache()
    yield
    explain.clear_cache()


def test_returns_none_when_no_model_is_loaded(monkeypatch):
    monkeypatch.setattr(ml_service, "_load", lambda name: None)
    result = explain.explain_safety_score([50, 12, 0.1, 30, 20])
    assert result is None


def test_returns_a_base_value_and_per_feature_contribution():
    result = explain.explain_safety_score([50, 12, 0.1, 30, 20])
    if result is None:
        pytest.skip("safety_rf.joblib not present in this environment")
    assert "base_value" in result
    assert set(result["contributions"]) == set(explain.SAFETY_FEATURE_NAMES)
    assert all(isinstance(v, float) for v in result["contributions"].values())


def test_contributions_sum_to_the_actual_prediction():
    """The core SHAP guarantee: base_value + sum(contributions) reproduces the
    model's own prediction for that input (within rounding)."""
    features = [70.0, 14, 0.3, 60.0, 20.0]
    result = explain.explain_safety_score(features)
    if result is None:
        pytest.skip("safety_rf.joblib not present in this environment")

    predicted = ml_service.predict_safety_score(features)
    reconstructed = result["base_value"] + sum(result["contributions"].values())
    assert reconstructed == pytest.approx(predicted, abs=0.5)


def test_different_inputs_produce_different_explanations():
    safe = explain.explain_safety_score([10.0, 12, 0.0, 10.0, 5.0])
    risky = explain.explain_safety_score([100.0, 2, 0.9, 90.0, 80.0])
    if safe is None or risky is None:
        pytest.skip("safety_rf.joblib not present in this environment")
    assert safe["contributions"] != risky["contributions"]


def test_higher_risk_inputs_get_more_negative_contributions_overall():
    """Not a per-feature guarantee, but the aggregate direction should make
    sense: a clearly worse situation should pull the score down overall."""
    safe = explain.explain_safety_score([5.0, 12, 0.0, 5.0, 5.0])
    dangerous = explain.explain_safety_score([100.0, 2, 1.0, 100.0, 100.0])
    if safe is None or dangerous is None:
        pytest.skip("safety_rf.joblib not present in this environment")

    safe_total = sum(safe["contributions"].values())
    dangerous_total = sum(dangerous["contributions"].values())
    assert dangerous_total < safe_total


def test_explainer_is_cached_across_calls():
    explain.explain_safety_score([50, 12, 0.1, 30, 20])
    first = explain._explainer_cache.get("safety")
    explain.explain_safety_score([60, 13, 0.2, 40, 30])
    second = explain._explainer_cache.get("safety")
    assert first is second  # same object, not rebuilt


def test_concurrent_first_explain_is_thread_safe():
    """Same class of bug fixed in ml_service._load: several threads racing to
    build the TreeExplainer for the first time must not corrupt the cache."""
    import threading

    explain.clear_cache()
    results = []
    barrier = threading.Barrier(12)

    def worker():
        barrier.wait()
        results.append(explain.explain_safety_score([50, 12, 0.1, 30, 20]))

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(results) == 12
    non_none = [r for r in results if r is not None]
    if non_none:
        assert all(r["base_value"] == non_none[0]["base_value"] for r in non_none)


def test_safety_score_endpoint_includes_the_explanation(client, admin_headers, tourist_user):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/safety-score",
                   headers=admin_headers)
    assert r.status_code == 200
    breakdown = r.json()["breakdown"]
    assert "explanation" in breakdown
