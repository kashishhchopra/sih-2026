"""Geocode API (app/api/maps.py)."""


def test_geocode_known_place(client, tourist_headers):
    r = client.get("/api/maps/geocode", params={"place": "Kamakhya Temple"}, headers=tourist_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["lat"] is not None and body["lng"] is not None


def test_geocode_unknown_place_returns_null_not_a_guess(client, tourist_headers):
    r = client.get("/api/maps/geocode", params={"place": "Nowhereville Xyzzy"}, headers=tourist_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["lat"] is None and body["lng"] is None


def test_geocode_requires_auth(client):
    r = client.get("/api/maps/geocode", params={"place": "Delhi"})
    assert r.status_code == 401
