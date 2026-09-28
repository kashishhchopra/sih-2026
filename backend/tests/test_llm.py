"""Open-ended language-model backend (services/llm.py) and its wiring into
the copilot's intent router."""
import pytest

from app.services import copilot, llm
from tests.conftest import make_tourist


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# ---------------------------------------------------------------- provider
def test_no_provider_in_test_environment():
    # Tests must never reach a real model (local or cloud): hermetic by
    # construction, same gate as the Nominatim geocoder.
    assert llm.active_provider() is None
    assert llm.complete("system", "user") is None


def test_auto_prefers_a_configured_cloud_key_over_the_local_model(monkeypatch):
    monkeypatch.setattr(llm.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "sk-test")
    assert llm.active_provider() == "anthropic"

    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm.settings, "OPENAI_API_KEY", "sk-test")
    assert llm.active_provider() == "openai"


def test_auto_falls_back_to_local_ollama_when_reachable(monkeypatch):
    monkeypatch.setattr(llm.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "auto")
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(llm.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm, "_ollama_reachable", lambda: True)
    assert llm.active_provider() == "ollama"

    monkeypatch.setattr(llm, "_ollama_reachable", lambda: False)
    assert llm.active_provider() is None


def test_provider_none_disables_open_ended_answers(monkeypatch):
    monkeypatch.setattr(llm.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "none")
    assert llm.active_provider() is None


def test_ollama_completion(monkeypatch):
    monkeypatch.setattr(llm.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(llm.httpx, "post",
                        lambda *a, **k: _FakeResponse({"message": {"content": " Bihu is a festival. "}}))
    assert llm.complete("sys", "what is bihu") == "Bihu is a festival."


def test_completion_failure_returns_none_not_a_placeholder(monkeypatch):
    monkeypatch.setattr(llm.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "ollama")

    def _boom(*a, **k):
        raise llm.httpx.ConnectError("model is down")

    monkeypatch.setattr(llm.httpx, "post", _boom)
    # None, so the caller can fall back -- never a fabricated answer.
    assert llm.complete("sys", "anything") is None


# ---------------------------------------------------------------- routing
@pytest.fixture
def _llm_on(monkeypatch):
    """Pretend a model is available and echo back the prompt it was given."""
    captured = {}

    def _fake_complete(system, user):
        captured["system"] = system
        captured["user"] = user
        return "An open-ended answer."

    monkeypatch.setattr(copilot.llm, "complete", _fake_complete)
    return captured


def test_unmatched_question_is_answered_by_the_model(db, _llm_on):
    t = make_tourist(db, name="Aarav")
    result = copilot.answer_tourist_question(db, t, "what is the Bihu festival about?")
    assert result["answer"] == "An open-ended answer."
    assert result["source"] == "llm"
    assert result["handled"] is True


def test_model_prompt_is_grounded_in_the_tourists_real_context(db, _llm_on):
    t = make_tourist(db, name="Aarav", itinerary=[{"name": "Kaziranga", "lat": 26.5, "lng": 93.1}])
    t.hotel = "Hotel Dynasty"
    db.commit()
    copilot.answer_tourist_question(db, t, "what should I pack?")
    prompt = _llm_on["user"]
    assert "Aarav" in prompt
    assert "Kaziranga" in prompt
    assert "Hotel Dynasty" in prompt
    assert "what should I pack?" in prompt


def test_safety_critical_questions_never_reach_the_model(db, monkeypatch):
    """The whole point of the two-layer design: a hospital question must be
    answered from real rows, never generated."""
    called = False

    def _should_not_be_called(system, user):
        nonlocal called
        called = True
        return "GENERATED"

    monkeypatch.setattr(copilot.llm, "complete", _should_not_be_called)
    t = make_tourist(db)
    for question in ("where is the nearest hospital?", "find a pharmacy", "find a cab",
                     "show my itinerary", "am I on the correct route?",
                     "call emergency services", "what should I do in an emergency?"):
        answer = copilot.answer_tourist_question(db, t, question)["answer"]
        assert answer != "GENERATED", question
    assert called is False


def test_falls_back_to_capability_list_when_no_model_is_available(db):
    t = make_tourist(db)
    result = copilot.answer_tourist_question(db, t, "tell me a joke")
    assert result["handled"] is False
    assert "tell me a joke" in result["answer"]  # reflects back what was heard


# ---------------------------------------------------------------- precision
def test_open_questions_are_no_longer_hijacked_by_keyword_intents(db, _llm_on):
    """Regression: these all contain an intent keyword ("doctor", "safe",
    "police", "help me") but are genuine open questions, and used to get a
    canned answer instead of a real one."""
    t = make_tourist(db)
    for question in (
        "do I need a doctor for a mosquito bite?",
        "is it safe to travel alone as a woman at night?",
        "how do I say thank you in Assamese?",
        "help me find a good vegetarian restaurant",
        "what happens if I lose my passport?",
    ):
        result = copilot.answer_tourist_question(db, t, question)
        assert result.get("source") == "llm", f"{question!r} was hijacked by an intent handler"
