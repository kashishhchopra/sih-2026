"""Translation API (app/api/translate.py)."""
from app.services import translation


def test_list_languages(client, tourist_headers):
    r = client.get("/api/translate/languages", headers=tourist_headers)
    assert r.status_code == 200
    assert "hi" in r.json()


def test_list_phrases(client, tourist_headers):
    r = client.get("/api/translate/phrases", headers=tourist_headers)
    assert r.status_code == 200
    assert "need_doctor" in r.json()


def test_translate_phrase(client, tourist_headers):
    r = client.post("/api/translate/phrase", headers=tourist_headers,
                    json={"phrase_id": "need_doctor", "target_lang": "hi"})
    assert r.status_code == 200
    assert r.json()["demo"] is False


def test_translate_text_uses_free_fallback_with_no_key(client, tourist_headers, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"responseData": {"translatedText": "Bonjour", "match": 1.0}}

    monkeypatch.setattr(translation.settings, "GOOGLE_TRANSLATE_API_KEY", "")
    monkeypatch.setattr(translation.httpx, "get", lambda *a, **k: FakeResponse())
    r = client.post("/api/translate/text", headers=tourist_headers,
                    json={"text": "hello", "target_lang": "fr"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert body["text"] == "Bonjour"


def test_translate_text_demo_mode_when_unreachable(client, tourist_headers, monkeypatch):
    import httpx as httpx_module

    def _raise(*a, **k):
        raise httpx_module.ConnectTimeout("timed out")

    monkeypatch.setattr(translation.settings, "GOOGLE_TRANSLATE_API_KEY", "")
    monkeypatch.setattr(translation.httpx, "get", _raise)
    r = client.post("/api/translate/text", headers=tourist_headers,
                    json={"text": "hello", "target_lang": "fr"})
    assert r.status_code == 200
    assert r.json()["demo"] is True


def test_translate_requires_auth(client):
    r = client.get("/api/translate/languages")
    assert r.status_code == 401


def test_guide_categories(client, tourist_headers):
    r = client.get("/api/translate/guide/categories", headers=tourist_headers)
    assert r.status_code == 200
    assert "greetings" in r.json()


def test_guide_phrases_for_category(client, tourist_headers):
    r = client.get("/api/translate/guide/greetings", headers=tourist_headers)
    assert r.status_code == 200
    assert "hello" in r.json()


def test_guide_phrase_translation(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "greetings", "phrase_id": "hello", "target_lang": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert body["text"]


def test_guide_unknown_phrase_is_reported_not_guessed(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "greetings", "phrase_id": "nonexistent", "target_lang": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is True
    assert body["text"] is None


def test_guide_directions_where_is_this_uses_real_location(client, tourist_headers):
    # Owner Tourist (see conftest.make_tourist) has no zone around its
    # default coordinates, so this should report the open-area template.
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "directions", "phrase_id": "where_is_this", "target_lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert "safety status" in body["text"]


def test_guide_directions_how_far_reports_real_nearest_units(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "directions", "phrase_id": "how_far", "target_lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert "Nearest hospital" in body["text"]


def test_guide_food_reports_no_data_honestly_when_none_found(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "food", "phrase_id": "recommend_local_food", "target_lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"]  # never empty -- either a real list or the honest "none found" text


def test_guide_medical_category(client, tourist_headers):
    r = client.get("/api/translate/guide/medical", headers=tourist_headers)
    assert r.status_code == 200
    assert "high_fever" in r.json()


def test_guide_medical_phrase_translation(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "medical", "phrase_id": "high_fever", "target_lang": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert body["text"] == "मुझे तेज़ बुखार है।"


def test_guide_taxi_category(client, tourist_headers):
    r = client.get("/api/translate/guide/taxi", headers=tourist_headers)
    assert r.status_code == 200
    assert "use_meter" in r.json()


def test_guide_shopping_negotiation_phrases(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "shopping", "phrase_id": "lower_price", "target_lang": "en"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert body["text"] == "Can you lower the price a little?"


def test_guide_greetings_unaffected_by_location_routing(client, tourist_headers):
    r = client.post("/api/translate/guide/phrase", headers=tourist_headers,
                    json={"category": "greetings", "phrase_id": "hello", "target_lang": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["demo"] is False
    assert body["text"] == "नमस्ते"
