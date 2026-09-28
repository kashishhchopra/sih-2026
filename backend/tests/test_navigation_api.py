"""Navigation guidance API (app/api/tourists.py get_navigation)."""


def test_navigation_returns_guidance(client, tourist_headers, tourist_user):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/navigation", headers=tourist_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["has_destination"] is True
    assert "instruction" in body


def test_navigation_forbidden_for_other_tourist(client, tourist_headers, db):
    from tests.conftest import make_tourist

    other = make_tourist(db, name="Someone Else")
    r = client.get(f"/api/tourists/{other.id}/navigation", headers=tourist_headers)
    assert r.status_code == 403


def test_navigation_404_for_unknown_tourist(client, tourist_headers, tourist_user):
    r = client.get("/api/tourists/999999/navigation", headers=tourist_headers)
    assert r.status_code in (403, 404)


def test_navigation_requires_auth(client, tourist_user):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/navigation")
    assert r.status_code == 401
