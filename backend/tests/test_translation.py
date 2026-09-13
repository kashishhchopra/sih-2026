"""Translation service: phrasebook + free-text translation (no
GOOGLE_TRANSLATE_API_KEY configured in tests -- see services/translation.py).
Free-text tests mock the MyMemory fallback request (same pattern as
test_weather.py/test_currency.py) so they never depend on real network
access or that free service's live availability/quota."""
import httpx

from app.services import translation


def test_translate_known_phrase_into_hindi():
    result = translation.translate_phrase("need_doctor", "hi")
    assert result["demo"] is False  # curated phrasebook text, not a live call
    assert "डॉक्टर" in result["text"]


def test_translate_known_phrase_into_all_supported_languages():
    for lang in translation.SUPPORTED_LANGUAGES:
        result = translation.translate_phrase("call_police", lang)
        assert result["text"]


def test_translate_unknown_phrase_id():
    result = translation.translate_phrase("not_a_real_phrase", "hi")
    assert result["text"] is None
    assert result["demo"] is True
    assert "error" in result


class _FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_translate_text_uses_free_mymemory_fallback_with_no_key(monkeypatch):
    monkeypatch.setattr(translation.settings, "GOOGLE_TRANSLATE_API_KEY", "")
    monkeypatch.setattr(
        translation.httpx, "get",
        lambda *a, **k: _FakeResponse({
            "responseData": {"translatedText": "Où est la gare ?", "match": 0.98},
        }),
    )
    result = translation.translate_text("Where is the train station?", "fr")
    assert result["demo"] is False
    assert result["text"] == "Où est la gare ?"


def test_translate_text_prefers_live_mt_match_over_bad_memory_match(monkeypatch):
    # Regression test for a real observed failure: MyMemory's top-level
    # translatedText can be a wrong stored phrase with a high similarity
    # score, while its own `matches` list carries the correct live MT
    # translation -- that one must win.
    monkeypatch.setattr(translation.settings, "GOOGLE_TRANSLATE_API_KEY", "")
    monkeypatch.setattr(
        translation.httpx, "get",
        lambda *a, **k: _FakeResponse({
            "responseData": {"translatedText": "Bharthana\nKa time", "match": 0.87},
            "matches": [
                {"translation": "Bharthana\nKa time", "created-by": "MateCat", "match": 0.87},
                {"translation": "सबसे नज़दीकी रेलवे स्टेशन कहाँ है?", "created-by": "MT!", "match": 0.85},
            ],
        }),
    )
    result = translation.translate_text("Where is the nearest train station?", "hi")
    assert result["demo"] is False
    assert result["text"] == "सबसे नज़दीकी रेलवे स्टेशन कहाँ है?"


def test_translate_text_rejects_garbled_mymemory_output(monkeypatch):
    # Regression test for a real observed failure: MyMemory can return bare
    # '?' characters for a non-Latin-script SOURCE language -- that must be
    # treated as a failure, never shown to a tourist as a translation.
    monkeypatch.setattr(translation.settings, "GOOGLE_TRANSLATE_API_KEY", "")
    monkeypatch.setattr(
        translation.httpx, "get",
        lambda *a, **k: _FakeResponse({
            "responseData": {"translatedText": "??????", "match": 0.85},
            "matches": [{"translation": "??????", "created-by": "MT!", "match": 0.85}],
        }),
    )
    result = translation.translate_text("नमस्ते", "en", source_lang="hi")
    assert result["demo"] is True


def test_translate_text_demo_mode_when_every_backend_is_unreachable(monkeypatch):
    monkeypatch.setattr(translation.settings, "GOOGLE_TRANSLATE_API_KEY", "")

    def _raise(*a, **k):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(translation.httpx, "get", _raise)
    result = translation.translate_text("Where is the train station?", "fr")
    assert result["demo"] is True
    assert result["text"] == "Where is the train station?"
    assert "note" in result
