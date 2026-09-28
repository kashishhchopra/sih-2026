"""Liveness verification service (services/liveness.py)."""
import base64
import hashlib
import io
from datetime import timedelta

from PIL import Image

from app.core.time import utc_now
from app.models.liveness import LivenessVerification
from app.schemas.liveness import LivenessVerifyRequest
from app.services import liveness
from tests.conftest import make_tourist


def _photo_data_uri(size=(150, 150), color=(200, 30, 30)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def test_verify_liveness_accepts_all_three_steps(db):
    photo = _photo_data_uri()
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=photo,
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    result = liveness.verify_liveness(db, req)
    assert result.success is True
    assert result.verified is True
    assert result.steps_completed == 3
    assert result.verification_token is not None

    row = db.query(LivenessVerification).filter(
        LivenessVerification.verification_token == result.verification_token
    ).first()
    assert row is not None
    assert row.verified is True
    assert row.consumed is False
    assert row.photo_sha256 == hashlib.sha256(base64.b64decode(photo.split(",", 1)[1])).hexdigest()


def test_verify_liveness_rejects_incomplete_steps(db):
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=_photo_data_uri(),
        steps=["turn_right"], liveness_score=0.9,
    )
    result = liveness.verify_liveness(db, req)
    assert result.verified is False
    assert result.verification_token is None
    assert result.steps_completed == 1


def test_verify_liveness_rejects_duplicate_steps_as_incomplete(db):
    # Sending the same step 3 times must not count as 3 distinct steps --
    # otherwise "turn right" three times would pass as a full check.
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=_photo_data_uri(),
        steps=["turn_right", "turn_right", "turn_right"], liveness_score=0.9,
    )
    result = liveness.verify_liveness(db, req)
    assert result.verified is False
    assert result.steps_completed == 1


def test_verify_liveness_rejects_low_score_even_with_all_steps(db):
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=_photo_data_uri(),
        steps=["turn_right", "look_up", "nod"], liveness_score=0.1,
    )
    result = liveness.verify_liveness(db, req)
    assert result.verified is False
    assert result.verification_token is None


def test_verify_liveness_rejects_corrupt_photo(db):
    # Enough bytes to clear the size floor, but not a real image -- must be
    # caught by the actual image-decode check, not the byte-count check.
    junk = base64.b64encode(b"not a real image" * 40).decode()
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=f"data:image/jpeg;base64,{junk}",
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    result = liveness.verify_liveness(db, req)
    assert result.success is False
    assert result.verified is False
    assert "could not be read" in result.message


def test_verify_liveness_rejects_undersized_photo(db):
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=_photo_data_uri(size=(20, 20)),
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    result = liveness.verify_liveness(db, req)
    assert result.success is False
    assert "too small" in result.message


def test_verify_liveness_never_raises_on_malformed_data_uri(db):
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo="not-a-data-uri-at-all",
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    result = liveness.verify_liveness(db, req)
    assert result.success is False
    assert result.verified is False


# ------------------------------------------------------- consume_verification
def test_consume_verification_binds_to_matching_photo(db):
    tourist = make_tourist(db)
    photo = _photo_data_uri()
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=photo,
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    issued = liveness.verify_liveness(db, req)

    ok = liveness.consume_verification(db, issued.verification_token, photo, tourist_id=tourist.id)
    assert ok is True

    row = db.query(LivenessVerification).filter(
        LivenessVerification.verification_token == issued.verification_token
    ).first()
    assert row.consumed is True
    assert row.tourist_id == tourist.id


def test_consume_verification_rejects_a_swapped_photo(db):
    # The exact anti-fraud property: a verified token can't be reused to
    # wave through a DIFFERENT photo than the one that passed the check.
    tourist = make_tourist(db)
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=_photo_data_uri(),
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    issued = liveness.verify_liveness(db, req)

    different_photo = _photo_data_uri(color=(10, 200, 10))
    ok = liveness.consume_verification(db, issued.verification_token, different_photo, tourist_id=tourist.id)
    assert ok is False


def test_consume_verification_rejects_reuse(db):
    t1, t2 = make_tourist(db, name="First"), make_tourist(db, name="Second")
    photo = _photo_data_uri()
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=photo,
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    issued = liveness.verify_liveness(db, req)

    assert liveness.consume_verification(db, issued.verification_token, photo, tourist_id=t1.id) is True
    # Second attempt with the same token must fail -- single-use.
    assert liveness.consume_verification(db, issued.verification_token, photo, tourist_id=t2.id) is False


def test_consume_verification_rejects_expired_token(db):
    tourist = make_tourist(db)
    photo = _photo_data_uri()
    req = LivenessVerifyRequest(
        session_id="sess-abc12345", photo=photo,
        steps=["turn_right", "look_up", "nod"], liveness_score=0.9,
    )
    issued = liveness.verify_liveness(db, req)

    row = db.query(LivenessVerification).filter(
        LivenessVerification.verification_token == issued.verification_token
    ).first()
    row.expires_at = utc_now() - timedelta(minutes=1)
    db.commit()

    assert liveness.consume_verification(db, issued.verification_token, photo, tourist_id=tourist.id) is False


def test_consume_verification_rejects_unknown_token(db):
    tourist = make_tourist(db)
    assert liveness.consume_verification(db, "not-a-real-token", _photo_data_uri(), tourist_id=tourist.id) is False
