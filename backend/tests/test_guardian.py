"""Trip Guardian / Family Live-Share (app/api/guardian.py)."""
from unittest.mock import patch

from tests.conftest import make_tourist, make_unit


def test_create_list_and_resolve_guardian(client, tourist_headers, tourist_user):
    tid = tourist_user.tourist_id
    r = client.post(f"/api/tourists/{tid}/guardians", headers=tourist_headers,
                    json={"guardian_name": "Mom", "guardian_contact": "+91-90000-11111"})
    assert r.status_code == 201
    token = r.json()["token"]

    listed = client.get(f"/api/tourists/{tid}/guardians", headers=tourist_headers)
    assert len(listed.json()) == 1

    # Public, unauthenticated resolve -- no headers.
    resolved = client.get(f"/api/guardian/{token}")
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["guardian_name"] == "Mom"
    assert body["tourist_name"] == tourist_user.full_name
    assert "last_lat" in body
    # Never leaks anything beyond live status.
    assert "document_number" not in body
    assert "phone" not in body


def test_revoke_guardian_blocks_further_resolution(client, tourist_headers, tourist_user):
    tid = tourist_user.tourist_id
    created = client.post(f"/api/tourists/{tid}/guardians", headers=tourist_headers,
                          json={"guardian_name": "Dad"})
    gid, token = created.json()["id"], created.json()["token"]

    revoked = client.post(f"/api/tourists/{tid}/guardians/{gid}/revoke", headers=tourist_headers)
    assert revoked.json()["revoked"] is True

    resolved = client.get(f"/api/guardian/{token}")
    assert resolved.status_code == 404


def test_resolve_unknown_token_404(client):
    assert client.get("/api/guardian/not-a-real-token").status_code == 404


def test_guardian_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Not Me")
    r = client.post(f"/api/tourists/{other.id}/guardians", headers=tourist_headers,
                    json={"guardian_name": "Intruder"})
    assert r.status_code == 403


def test_sos_notifies_active_guardians(client, tourist_headers, tourist_user, db):
    make_unit(db)
    tid = tourist_user.tourist_id
    client.post(f"/api/tourists/{tid}/guardians", headers=tourist_headers,
               json={"guardian_name": "Mom", "guardian_contact": "mom@example.com"})

    with patch("app.services.monitoring.notifications.get_channel") as mock_channel:
        r = client.post(f"/api/tourists/{tid}/sos", headers=tourist_headers,
                        json={"lat": 26.14, "lng": 91.73, "message": "help"})
        assert r.status_code == 200
        sent_to = [c.kwargs["to"] for c in mock_channel.return_value.send.call_args_list]
        assert "mom@example.com" in sent_to
