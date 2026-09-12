"""Translation service: phrasebook + demo-mode free text (no
GOOGLE_TRANSLATE_API_KEY configured in tests -- see services/translation.py)."""
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


def test_translate_text_demo_mode_returns_original_and_says_so():
    result = translation.translate_text("Where is the train station?", "fr")
    assert result["demo"] is True
    assert result["text"] == "Where is the train station?"
    assert "note" in result
