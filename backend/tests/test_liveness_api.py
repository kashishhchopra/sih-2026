"""Liveness verification API and its integration with registration
(POST /tourists/verify-liveness, and TouristCreate.liveness_token)."""
import base64
import io
from datetime import timedelta

from PIL import Image

from app.core.time import utc_now
from app.models.liveness import LivenessVerification


def _photo_data_uri(size=(150, 150), color=(50, 120, 200)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"


def _registration_payload(photo, **over):
    now = utc_now()
    base = {
        "full_name": "Liveness Tourist",
        "nationality": "Indian",
        "document_type": "aadhaar",
        "document_number": "123456788888",
        "phone": "9876543211",
        "photo": photo,
        "itinerary": [], "emergency_contacts": [],
        "trip_start": now.isoformat(),
        "trip_end": (now + timedelta(days=5)).isoformat(),
    }
    base.update(over)
    return base


def test_verify_liveness_endpoint_returns_a_token_for_a_full_pass(client):
    photo = _photo_data_uri()
    r = client.post("/api/tourists/verify-liveness", json={
        "session_id": "sess-abcdef01", "photo": photo,
        "steps": ["turn_right", "look_up", "nod"], "liveness_score": 0.87,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["steps_completed"] == 3
    assert body["verification_token"]


def test_verify_liveness_endpoint_requires_no_auth(client):
    # Runs before any account exists, same as registration itself.
    r = client.post("/api/tourists/verify-liveness", json={
        "session_id": "sess-abcdef01", "photo": _photo_data_uri(),
        "steps": ["turn_right"], "liveness_score": 0.0,
    })
    assert r.status_code == 200  # not 401 -- public, like POST /tourists


def test_verify_liveness_endpoint_rejects_bad_score_range(client):
    r = client.post("/api/tourists/verify-liveness", json={
        "session_id": "sess-abcdef01", "photo": _photo_data_uri(),
        "steps": ["turn_right"], "liveness_score": 1.5,
    })
    assert r.status_code == 422  # schema-level validation, not a 500


def test_registration_binds_a_valid_liveness_token_to_the_new_tourist(client, db):
    photo = _photo_data_uri()
    verify = client.post("/api/tourists/verify-liveness", json={
        "session_id": "sess-abcdef01", "photo": photo,
        "steps": ["turn_right", "look_up", "nod"], "liveness_score": 0.9,
    }).json()
    token = verify["verification_token"]

    r = client.post("/api/tourists", json=_registration_payload(photo, liveness_token=token))
    assert r.status_code == 201
    tourist_id = r.json()["id"]

    row = db.query(LivenessVerification).filter(
        LivenessVerification.verification_token == token
    ).first()
    assert row.consumed is True
    assert row.tourist_id == tourist_id


def test_registration_succeeds_without_any_liveness_token(client):
    # The core "never block signup" guarantee -- omitting it entirely (e.g.
    # a browser with no camera support) must not affect registration at all.
    r = client.post("/api/tourists", json=_registration_payload(_photo_data_uri()))
    assert r.status_code == 201


def test_registration_succeeds_with_an_invalid_liveness_token(client):
    # An expired/unknown/already-used token is silently ignored, not a
    # registration failure -- see services/liveness.py's docstring.
    r = client.post("/api/tourists", json=_registration_payload(
        _photo_data_uri(), liveness_token="totally-made-up-token",
    ))
    assert r.status_code == 201


def test_registration_ignores_a_token_issued_for_a_different_photo(client, db):
    # Someone could try to reuse a verified token while swapping in a
    # different (unverified) photo at the actual registration step -- the
    # registration must still succeed, but the verification row must NOT
    # get bound to this tourist, since it never matched their real photo.
    verified_photo = _photo_data_uri(color=(10, 10, 10))
    other_photo = _photo_data_uri(color=(250, 250, 250))
    token = client.post("/api/tourists/verify-liveness", json={
        "session_id": "sess-abcdef01", "photo": verified_photo,
        "steps": ["turn_right", "look_up", "nod"], "liveness_score": 0.9,
    }).json()["verification_token"]

    r = client.post("/api/tourists", json=_registration_payload(other_photo, liveness_token=token))
    assert r.status_code == 201

    row = db.query(LivenessVerification).filter(
        LivenessVerification.verification_token == token
    ).first()
    assert row.consumed is False
    assert row.tourist_id is None


def test_digital_id_and_qr_still_work_when_liveness_was_used(client):
    """Regression guard for the explicit checklist item: adding liveness
    must not disturb ID/QR issuance."""
    photo = _photo_data_uri()
    token = client.post("/api/tourists/verify-liveness", json={
        "session_id": "sess-abcdef01", "photo": photo,
        "steps": ["turn_right", "look_up", "nod"], "liveness_score": 0.9,
    }).json()["verification_token"]

    r = client.post("/api/tourists", json=_registration_payload(photo, liveness_token=token))
    body = r.json()
    assert body["digital_id"].startswith("STS-")
    assert body["photo"] == photo
