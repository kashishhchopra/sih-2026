"""Forgot/reset password flow and the notification channel it uses."""
from datetime import timedelta

import pytest

from app.core.security import verify_password
from app.core.time import utc_now
from app.models.password_reset import PasswordResetToken
from app.services import notifications


class _CapturingChannel:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append({"to": to, "subject": subject, "body": body})
        return True


@pytest.fixture
def capture(monkeypatch):
    channel = _CapturingChannel()
    monkeypatch.setitem(notifications._channels, "console", channel)
    return channel


def _extract_token(body: str) -> str:
    return body.split(": ")[-1]


# ---------------------------------------------------------------- forgot-password
def test_forgot_password_sends_a_notification(client, admin_user, capture):
    r = client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    assert r.status_code == 200
    assert len(capture.sent) == 1
    assert capture.sent[0]["to"] == "admin@test.gov"


def test_forgot_password_response_identical_for_unknown_email(client, admin_user, capture):
    """Must not reveal whether an email is registered."""
    known = client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.com"})
    assert known.json() == unknown.json()
    assert known.status_code == unknown.status_code == 200


def test_forgot_password_for_unknown_email_sends_nothing(client, capture):
    client.post("/api/auth/forgot-password", json={"email": "nobody@nowhere.com"})
    assert capture.sent == []


def test_forgot_password_persists_a_hashed_token_not_the_raw_one(client, admin_user, capture, db):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    raw_token = _extract_token(capture.sent[0]["body"])

    row = db.query(PasswordResetToken).one()
    assert row.token_hash != raw_token
    assert len(row.token_hash) == 64  # sha256 hex digest


def test_forgot_password_is_rate_limited(client, admin_user, capture):
    from app.core.config import settings
    for _ in range(settings.LOGIN_RATE_LIMIT):
        client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    r = client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    assert r.status_code == 429


# ---------------------------------------------------------------- reset-password
def test_reset_password_with_valid_token_changes_the_password(client, admin_user, capture, db):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})
    assert r.status_code == 204

    db.refresh(admin_user)
    assert verify_password("Newpass123!", admin_user.hashed_password)
    assert not verify_password("adminpass1", admin_user.hashed_password)


def test_old_password_no_longer_logs_in_after_reset(client, admin_user, capture):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})

    r = client.post("/api/auth/login", data={"username": "admin@test.gov", "password": "adminpass1"})
    assert r.status_code == 401


def test_new_password_logs_in_after_reset(client, admin_user, capture):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})

    r = client.post("/api/auth/login", data={"username": "admin@test.gov", "password": "Newpass123!"})
    assert r.status_code == 200


def test_reset_with_unknown_token_rejected(client):
    r = client.post("/api/auth/reset-password",
                    json={"token": "not-a-real-token", "new_password": "Newpass123!"})
    assert r.status_code == 400


def test_reset_token_cannot_be_reused(client, admin_user, capture):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Firstpass123!"})

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Secondpass123!"})
    assert r.status_code == 400


def test_expired_reset_token_rejected(client, admin_user, capture, db):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])

    row = db.query(PasswordResetToken).one()
    row.expires_at = utc_now() - timedelta(minutes=1)
    db.commit()

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})
    assert r.status_code == 400


def test_reset_rejects_a_weak_new_password(client, admin_user, capture):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "weak"})
    assert r.status_code == 422


def test_reset_password_is_audited(client, admin_user, capture, db):
    from app.models.audit import AuditLog

    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})

    assert db.query(AuditLog).filter_by(action="reset_password").count() == 1


# ---------------------------------------------------------------- session epoch
# JWT `iat` is floored to whole seconds on encode (see
# app/api/auth.py::_token_predates_epoch), so the epoch check can only ever
# distinguish tokens across a whole-second boundary -- these tests force a
# real one rather than relying on wall-clock luck between two fast HTTP calls.
def test_refresh_token_issued_before_reset_is_rejected_after_it(client, admin_user, capture):
    """A reset must kill every existing session, not just block new logins --
    otherwise a refresh token an attacker already holds (the reason the
    password is being reset) keeps working until it expires on its own."""
    import time

    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    time.sleep(1.1)

    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})

    # Clear the jar so this exercises the stale *body* token specifically,
    # not whatever cookie the client happens to be holding.
    client.cookies.clear()
    r = client.post("/api/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert r.status_code == 401


def test_access_token_issued_before_reset_is_rejected_after_it(client, admin_user, capture):
    import time

    login = client.post("/api/auth/login",
                        data={"username": "admin@test.gov", "password": "adminpass1"}).json()
    time.sleep(1.1)

    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {login['access_token']}"})
    assert r.status_code == 401


def test_a_fresh_login_after_reset_works_normally(client, admin_user, capture):
    client.post("/api/auth/forgot-password", json={"email": "admin@test.gov"})
    token = _extract_token(capture.sent[0]["body"])
    client.post("/api/auth/reset-password", json={"token": token, "new_password": "Newpass123!"})

    r = client.post("/api/auth/login", data={"username": "admin@test.gov", "password": "Newpass123!"})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200


# ---------------------------------------------------------------- notification channel
def test_console_channel_is_the_default(monkeypatch):
    monkeypatch.setattr(notifications.settings, "NOTIFICATION_CHANNEL", "console")
    channel = notifications.get_channel()
    assert isinstance(channel, notifications.ConsoleNotificationChannel)


def test_unknown_channel_name_falls_back_to_console(monkeypatch):
    monkeypatch.setattr(notifications.settings, "NOTIFICATION_CHANNEL", "sms-provider-not-configured")
    channel = notifications.get_channel()
    assert isinstance(channel, notifications.ConsoleNotificationChannel)


def test_console_channel_send_returns_true():
    channel = notifications.ConsoleNotificationChannel()
    assert channel.send("a@b.com", "subject", "body") is True
