"""Refresh token delivered via httpOnly cookie (app/api/auth.py)."""
from app.core.config import settings
from app.core.security import decode_refresh_token


def _login(client, email="admin@test.gov", password="adminpass1"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_login_sets_an_httponly_refresh_cookie(client, admin_user):
    r = _login(client)
    assert r.status_code == 200
    cookie = r.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert cookie is not None
    set_cookie_header = r.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header


def test_refresh_works_from_the_cookie_with_no_body(client, admin_user):
    _login(client)  # TestClient's cookie jar now holds the refresh cookie
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert r.json()["access_token"]


def test_refresh_still_accepts_a_body_token_for_back_compat(client, admin_user):
    login = _login(client).json()
    # Simulate a client with no cookie jar (e.g. a stored mobile client).
    # A per-request `cookies=` kwarg does NOT clear TestClient's persistent
    # jar (httpx treats it as ambiguous/deprecated) -- clearing the jar
    # directly is the only reliable way to simulate "no cookie sent".
    client.cookies.clear()
    r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 200


def test_refresh_with_neither_cookie_nor_body_is_rejected(client):
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401


def test_refresh_rotates_the_cookie(client, admin_user):
    first = _login(client)
    first_cookie = first.cookies.get(settings.REFRESH_COOKIE_NAME)
    r = client.post("/api/auth/refresh")
    new_cookie = r.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert new_cookie is not None
    assert new_cookie != first_cookie


def test_logout_clears_the_cookie_and_works_with_no_body(client, admin_user):
    _login(client)
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    # A cleared cookie is sent back with an empty value / immediate expiry.
    assert r.cookies.get(settings.REFRESH_COOKIE_NAME) in (None, "", '""')


def test_logout_via_cookie_actually_revokes_the_token(client, admin_user, db):
    login = _login(client).json()
    client.post("/api/auth/logout")

    jti = decode_refresh_token(login["refresh_token"])["jti"]
    from app.models.revoked_token import RevokedToken
    assert db.get(RevokedToken, jti) is not None
