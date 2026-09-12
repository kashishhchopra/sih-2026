"""Refresh-token issuance, rotation, revocation, and logout."""
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.models.revoked_token import RevokedToken


def test_login_returns_both_tokens(client, admin_user):
    body = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    assert body["access_token"] and body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_refresh_and_access_tokens_have_distinct_types():
    access = create_access_token("a@b.com", "admin")
    refresh, _jti, _exp = create_refresh_token("a@b.com", "admin")

    assert decode_access_token(access)["type"] == "access"
    assert decode_refresh_token(refresh)["type"] == "refresh"


def test_an_access_token_is_not_accepted_as_a_refresh_token():
    access = create_access_token("a@b.com", "admin")
    assert decode_refresh_token(access) is None


def test_a_refresh_token_is_not_accepted_as_an_access_token():
    refresh, _jti, _exp = create_refresh_token("a@b.com", "admin")
    assert decode_access_token(refresh) is None


def test_refresh_endpoint_issues_a_new_pair(client, admin_user):
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["access_token"] != login["access_token"]
    assert new["refresh_token"] != login["refresh_token"]


def test_refresh_rotates_out_the_old_token(client, admin_user, db):
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})

    old_jti = decode_refresh_token(login["refresh_token"])["jti"]
    assert db.get(RevokedToken, old_jti) is not None


def test_reusing_a_rotated_out_refresh_token_is_rejected(client, admin_user):
    # This test is specifically about replaying a stale *presented* token, so
    # it clears the client's cookie jar before each call and pins itself to
    # the body-only path -- otherwise the jar would auto-attach the freshly
    # rotated cookie from the first call and mask the stale body token.
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    client.cookies.clear()
    client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})

    client.cookies.clear()
    replay = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert replay.status_code == 401


def test_refresh_with_garbage_token_rejected(client):
    r = client.post("/api/auth/refresh", json={"refresh_token": "not.a.jwt"})
    assert r.status_code == 401


def test_refresh_for_a_deleted_user_is_rejected(client, admin_user, db):
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    db.delete(admin_user)
    db.commit()

    r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


def test_logout_revokes_the_refresh_token(client, admin_user, db):
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    r = client.post("/api/auth/logout", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 204

    jti = decode_refresh_token(login["refresh_token"])["jti"]
    assert db.get(RevokedToken, jti) is not None


def test_refresh_after_logout_is_rejected(client, admin_user):
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    client.post("/api/auth/logout", json={"refresh_token": login["refresh_token"]})

    r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


def test_logout_with_an_already_invalid_token_does_not_error(client):
    r = client.post("/api/auth/logout", json={"refresh_token": "garbage"})
    assert r.status_code == 204


def test_access_token_keeps_working_after_logout_until_natural_expiry(client, admin_user, admin_headers):
    """Documented trade-off: access tokens are short-lived and not checked
    against the revocation list per request. Logout revokes the refresh
    token (blocking new access tokens), not any already-issued access token."""
    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    client.post("/api/auth/logout", json={"refresh_token": login["refresh_token"]})

    r = client.get("/api/auth/me",
                   headers={"Authorization": f"Bearer {login['access_token']}"})
    assert r.status_code == 200


def test_purge_expired_revocations(db):
    from datetime import timedelta

    from app.api.auth import purge_expired_revocations
    from app.core.time import utc_now

    db.add(RevokedToken(jti="expired", expires_at=utc_now() - timedelta(days=1)))
    db.add(RevokedToken(jti="still-valid", expires_at=utc_now() + timedelta(days=1)))
    db.commit()

    deleted = purge_expired_revocations(db)
    assert deleted == 1
    assert db.get(RevokedToken, "expired") is None
    assert db.get(RevokedToken, "still-valid") is not None
