"""Translation API (app/api/translate.py)."""


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


def test_translate_text_demo_mode(client, tourist_headers):
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
