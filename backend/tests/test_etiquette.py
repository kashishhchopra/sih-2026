"""Cultural Etiquette Guide (services/etiquette.py + api/etiquette.py)."""
from app.services import etiquette


def test_list_topics_includes_expected_set():
    topics = etiquette.list_topics()
    assert "temples" in topics
    assert "tipping" in topics


def test_get_topic_in_english():
    result = etiquette.get_topic("temples", "en")
    assert result["demo"] is False
    assert "shoes" in result["text"]


def test_get_topic_in_hindi():
    result = etiquette.get_topic("dining", "hi")
    assert result["demo"] is False
    assert result["title"] == "भोजन"


def test_get_topic_falls_back_honestly_for_unreviewed_language():
    result = etiquette.get_topic("tipping", "fr")
    assert result["demo"] is True
    assert result["text"] == etiquette.get_topic("tipping", "en")["text"]


def test_unknown_topic_is_reported_not_guessed():
    result = etiquette.get_topic("nonexistent", "en")
    assert result["demo"] is True
    assert result["text"] is None


def test_topics_api_requires_auth(client):
    r = client.get("/api/etiquette/topics")
    assert r.status_code == 401


def test_topic_api(client, tourist_headers):
    r = client.get("/api/etiquette/temples", headers=tourist_headers, params={"lang": "en"})
    assert r.status_code == 200
    assert r.json()["demo"] is False
