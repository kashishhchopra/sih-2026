"""Tourist registration, serialization, and input validation."""
from datetime import timedelta

import pytest

from app.core.time import utc_now
from app.models.user import User


def _payload(**over):
    now = utc_now()
    base = {
        "full_name": "New Tourist",
        "nationality": "Indian",
        "document_type": "aadhaar",
        "document_number": "123456789999",
        "phone": "9876543210",
        "photo": "data:image/png;base64,iVBORw0KGgo=",
        "itinerary": [{"name": "Stop", "lat": 26.14, "lng": 91.73}],
        "emergency_contacts": [{"name": "Kin", "phone": "+91-1", "relation": "family"}],
        "trip_start": now.isoformat(),
        "trip_end": (now + timedelta(days=5)).isoformat(),
    }
    base.update(over)
    return base


def test_registration_requires_a_photo(client):
    payload = _payload()
    del payload["photo"]
    r = client.post("/api/tourists", json=payload)
    assert r.status_code == 422


def test_registration_mints_a_digital_id(client):
    r = client.post("/api/tourists", json=_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["digital_id"].startswith("STS-")
    assert body["is_valid"] is True


def test_registration_response_has_no_orm_internals(client):
    body = client.post("/api/tourists", json=_payload()).json()
    assert "_sa_instance_state" not in body


def test_registration_seeds_the_hash_chain(client, admin_headers):
    tid = client.post("/api/tourists", json=_payload()).json()["id"]
    chain = client.get(f"/api/tourists/{tid}/chain", headers=admin_headers).json()
    assert len(chain) == 1 and chain[0]["event"] == "ID_ISSUED"
    assert client.get(f"/api/tourists/{tid}/chain/verify",
                      headers=admin_headers).json()["valid"] is True


def test_registration_with_credentials_creates_a_login(client, db):
    r = client.post("/api/tourists", json=_payload(
        email="new@test.com", password="Strongpass1!"))
    assert r.status_code == 201
    user = db.query(User).filter_by(email="new@test.com").one()
    assert user.role == "tourist" and user.tourist_id == r.json()["id"]


def test_duplicate_email_rejected(client):
    client.post("/api/tourists", json=_payload(email="dup@test.com",
                                               password="Strongpass1!"))
    r = client.post("/api/tourists", json=_payload(email="dup@test.com",
                                                   password="Strongpass1!"))
    assert r.status_code == 400


# ---------------------------------------------------------------- validation
def test_trip_end_before_start_rejected(client):
    now = utc_now()
    r = client.post("/api/tourists", json=_payload(
        trip_start=now.isoformat(), trip_end=(now - timedelta(days=1)).isoformat()))
    assert r.status_code == 422


def test_weak_password_rejected(client):
    r = client.post("/api/tourists", json=_payload(email="w@test.com", password="weak"))
    assert r.status_code == 422


def test_email_without_password_rejected(client):
    assert client.post("/api/tourists",
                       json=_payload(email="x@test.com")).status_code == 422


@pytest.mark.parametrize("bad_doc", ["driverslicense", "ration_card", ""])
def test_invalid_document_type_rejected(client, bad_doc):
    assert client.post("/api/tourists",
                       json=_payload(document_type=bad_doc)).status_code == 422


# --------------------------------------- Smart Identity & Contact Validation
# Backend must reject bad identity/contact values even if a client bypasses
# the frontend's own real-time input restriction entirely.
@pytest.mark.parametrize("bad_name", ["Rahul123", "Rahul@Sharma", "Rahul-Sharma", "Rahul_123"])
def test_invalid_name_rejected(client, bad_name):
    r = client.post("/api/tourists", json=_payload(full_name=bad_name))
    assert r.status_code == 422
    assert "letters and spaces" in r.text


@pytest.mark.parametrize("bad_phone", [
    "987654321", "98765432101", "5123456789", "98765abc10", "98765 43210", "98765-43210",
])
def test_invalid_phone_rejected(client, bad_phone):
    r = client.post("/api/tourists", json=_payload(phone=bad_phone))
    assert r.status_code == 422
    assert "10-digit mobile number" in r.text


@pytest.mark.parametrize("bad_aadhaar", ["12345678901", "1234567890123", "1234abcd9012", "1234-5678-9012"])
def test_invalid_aadhaar_rejected(client, bad_aadhaar):
    r = client.post("/api/tourists", json=_payload(document_number=bad_aadhaar))
    assert r.status_code == 422
    assert "exactly 12 digits" in r.text


def test_invalid_pan_rejected(client):
    r = client.post("/api/tourists",
                    json=_payload(document_type="pan", document_number="ABCDE12345"))
    assert r.status_code == 422
    assert "PAN must contain" in r.text


def test_invalid_voterid_rejected(client):
    r = client.post("/api/tourists",
                    json=_payload(document_type="voterid", document_number="ABC123456"))
    assert r.status_code == 422
    assert "Voter ID must contain" in r.text


def test_lowercase_pan_is_normalized_to_uppercase_and_accepted(client):
    r = client.post("/api/tourists",
                    json=_payload(document_type="pan", document_number="abcde1234f"))
    assert r.status_code == 201
    assert r.json()["document_number"] == "ABCDE1234F"


def test_name_whitespace_is_trimmed_and_collapsed(client):
    r = client.post("/api/tourists", json=_payload(full_name="  Rahul   Sharma  "))
    assert r.status_code == 201
    assert r.json()["full_name"] == "Rahul Sharma"


@pytest.mark.parametrize("lat,lng", [(91.0, 91.7), (26.1, 181.0), (-91.0, 0.0)])
def test_out_of_range_waypoint_rejected(client, lat, lng):
    r = client.post("/api/tourists",
                    json=_payload(itinerary=[{"name": "Bad", "lat": lat, "lng": lng}]))
    assert r.status_code == 422


def test_registration_is_rate_limited(client):
    from app.core.config import settings
    for _ in range(settings.REGISTRATION_RATE_LIMIT):
        client.post("/api/tourists", json=_payload())
    assert client.post("/api/tourists", json=_payload()).status_code == 429


# ---------------------------------------------------------------- location input
@pytest.mark.parametrize("body", [
    {"lat": 200.0, "lng": 91.7, "speed_kmh": 5},
    {"lat": 26.1, "lng": 400.0, "speed_kmh": 5},
    {"lat": 26.1, "lng": 91.7, "speed_kmh": -5},
    {"lat": 26.1, "lng": 91.7, "speed_kmh": 5000},
])
def test_invalid_location_payload_rejected(client, admin_headers, tourist_user, body):
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/location",
                    json=body, headers=admin_headers)
    assert r.status_code == 422


def test_qr_code_is_returned_as_data_uri(client, tourist_user, admin_headers):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/qr", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["qr_png_base64"].startswith("data:image/png;base64,")


def test_missing_tourist_returns_404(client, admin_headers):
    assert client.get("/api/tourists/9999", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- passport/visa
def _passport_payload(**over):
    now = utc_now()
    base = {
        "document_type": "passport", "nationality": "Japanese",
        "document_number": "T1234567",
        "visa_type": "Tourist", "visa_expiry": (now + timedelta(days=10)).isoformat(),
    }
    base.update(over)
    return _payload(**base)


def test_passport_registration_requires_visa_fields(client):
    payload = _payload(document_type="passport", nationality="Japanese",
                       document_number="TK1234567")
    r = client.post("/api/tourists", json=payload)
    assert r.status_code == 422


def test_passport_registration_with_visa_fields_succeeds(client):
    r = client.post("/api/tourists", json=_passport_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["nationality_code"] == "JP"
    assert body["visa_type"] == "Tourist"


def test_visa_expiring_before_trip_end_is_rejected(client):
    now = utc_now()
    payload = _passport_payload(
        trip_end=(now + timedelta(days=20)).isoformat(),
        visa_expiry=(now + timedelta(days=5)).isoformat(),  # expires mid-trip
    )
    r = client.post("/api/tourists", json=payload)
    assert r.status_code == 422


def test_aadhaar_registration_does_not_require_visa_fields(client):
    r = client.post("/api/tourists", json=_payload())  # document_type="aadhaar"
    assert r.status_code == 201


def test_passport_registration_appends_a_visa_recorded_chain_block(client, admin_headers):
    tid = client.post("/api/tourists", json=_passport_payload()).json()["id"]
    r = client.get(f"/api/tourists/{tid}/chain", headers=admin_headers)
    events = [b["event"] for b in r.json()]
    assert "VISA_RECORDED" in events


def test_aadhaar_registration_has_no_visa_recorded_block(client, admin_headers):
    tid = client.post("/api/tourists", json=_payload()).json()["id"]
    r = client.get(f"/api/tourists/{tid}/chain", headers=admin_headers)
    events = [b["event"] for b in r.json()]
    assert "VISA_RECORDED" not in events
