"""Authentication, token handling, and role-based authorization."""
from datetime import timedelta

import pytest
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)


# ---------------------------------------------------------------- passwords
def test_password_hash_round_trip():
    h = hash_password("correct horse1")
    assert h != "correct horse1"
    assert verify_password("correct horse1", h) is True
    assert verify_password("wrong password1", h) is False


def test_password_hashes_are_salted():
    assert hash_password("samepass1") != hash_password("samepass1")


def test_verify_password_rejects_garbage_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_bcrypt_72_byte_limit_does_not_raise():
    long_pw = "a1" * 100
    assert verify_password(long_pw, hash_password(long_pw)) is True


@pytest.mark.parametrize("weak", [
    "short1",           # too short
    "alllettersonly",   # no digit, no uppercase, no symbol
    "12345678",         # no letters at all
    "",                 # empty
    "goodpass123",      # letters + digits, but no uppercase and no symbol
    "GOODPASS123",      # no lowercase, no symbol
    "GoodPass!",        # no digit
    "GoodPass123",      # no symbol
])
def test_weak_passwords_rejected(weak):
    with pytest.raises(ValueError):
        validate_password_strength(weak)


def test_strong_password_accepted():
    validate_password_strength("GoodPass123!")


def test_password_missing_uppercase_gives_a_specific_message():
    with pytest.raises(ValueError, match="uppercase"):
        validate_password_strength("goodpass123!")


def test_password_missing_lowercase_gives_a_specific_message():
    with pytest.raises(ValueError, match="lowercase"):
        validate_password_strength("GOODPASS123!")


def test_password_missing_digit_gives_a_specific_message():
    with pytest.raises(ValueError, match="number"):
        validate_password_strength("GoodPassword!")


def test_password_missing_symbol_gives_a_specific_message():
    with pytest.raises(ValueError, match="special character"):
        validate_password_strength("GoodPass123")


# ---------------------------------------------------------------- JWT
def test_token_round_trip():
    token = create_access_token("a@b.com", "admin", tourist_id=None)
    payload = decode_access_token(token)
    assert payload["sub"] == "a@b.com"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_expired_token_rejected():
    assert decode_access_token(
        create_access_token("a@b.com", "admin", expires_minutes=-1)
    ) is None


def test_token_signed_with_another_key_rejected():
    forged = jwt.encode({"sub": "a@b.com", "role": "admin", "type": "access"},
                        "a-completely-different-key", algorithm="HS256")
    assert decode_access_token(forged) is None


def test_non_access_token_type_rejected():
    other = jwt.encode({"sub": "a@b.com", "role": "admin", "type": "refresh"},
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert decode_access_token(other) is None


def test_garbage_token_rejected():
    assert decode_access_token("not.a.token") is None


# ---------------------------------------------------------------- login endpoint
def test_login_success(client, admin_user):
    r = client.post("/api/auth/login",
                    data={"username": "admin@test.gov", "password": "adminpass1"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_login_wrong_password(client, admin_user):
    r = client.post("/api/auth/login",
                    data={"username": "admin@test.gov", "password": "wrongpass1"})
    assert r.status_code == 401


def test_login_unknown_email_gives_same_error(client, admin_user):
    """Response must not reveal whether the account exists."""
    unknown = client.post("/api/auth/login",
                          data={"username": "nobody@test.gov", "password": "x1"})
    wrong = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "wrongpass1"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_login_is_rate_limited(client, admin_user):
    limit = settings.LOGIN_RATE_LIMIT
    for _ in range(limit):
        client.post("/api/auth/login",
                    data={"username": "admin@test.gov", "password": "wrongpass1"})
    r = client.post("/api/auth/login",
                    data={"username": "admin@test.gov", "password": "adminpass1"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


def test_me_returns_current_user(client, admin_headers):
    r = client.get("/api/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "admin@test.gov"


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------- authorization
def test_admin_endpoints_reject_tourists(client, tourist_headers):
    for path in ["/api/tourists", "/api/incidents", "/api/analytics/summary",
                 "/api/audit-log", "/api/alerts"]:
        assert client.get(path, headers=tourist_headers).status_code == 403, path


def test_admin_endpoints_reject_anonymous(client):
    for path in ["/api/tourists", "/api/incidents", "/api/analytics/summary"]:
        assert client.get(path, headers={}).status_code == 401, path


def test_tourist_cannot_read_another_tourists_record(client, db, tourist_headers):
    from tests.conftest import make_tourist
    other = make_tourist(db, name="Someone Else")
    r = client.get(f"/api/tourists/{other.id}", headers=tourist_headers)
    assert r.status_code == 403


def test_tourist_can_read_own_record(client, tourist_user, tourist_headers):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}", headers=tourist_headers)
    assert r.status_code == 200
    assert r.json()["full_name"] == "Owner Tourist"


def test_tourist_cannot_post_location_for_another(client, db, tourist_headers):
    from tests.conftest import make_tourist
    other = make_tourist(db, name="Victim")
    r = client.post(f"/api/tourists/{other.id}/location",
                    json={"lat": 26.1, "lng": 91.7, "speed_kmh": 5},
                    headers=tourist_headers)
    assert r.status_code == 403


def test_tourist_cannot_trigger_sos_for_another(client, db, tourist_headers):
    from tests.conftest import make_tourist
    other = make_tourist(db, name="Victim")
    r = client.post(f"/api/tourists/{other.id}/sos",
                    json={"lat": 26.1, "lng": 91.7, "message": "spoofed"},
                    headers=tourist_headers)
    assert r.status_code == 403


def test_tourist_cannot_mark_someone_missing(client, db, tourist_headers):
    from tests.conftest import make_tourist
    other = make_tourist(db, name="Victim")
    r = client.post(f"/api/tourists/{other.id}/mark-missing", headers=tourist_headers)
    assert r.status_code == 403
