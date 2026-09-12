"""Server side of the tourist-registration liveness check.

The actual 3-step head-movement detection runs in the browser, in real
time, against the live camera feed (frontend/src/lib/liveness.js +
hooks/useLivenessCheck.js, using MediaPipe's Face Landmarker) -- a server
has no access to a webcam feed it isn't sent, so it cannot redo that
tracking itself. What this module *can* and does check honestly:

  * the reported result is structurally sane (all 3 known steps present,
    each only once, score in range) rather than trivially fabricated,
  * the submitted photo actually decodes as a real image of a plausible
    size, not empty/corrupt/absurdly tiny data,
  * whatever photo is later submitted at registration is the *exact same*
    one this check was issued for (by comparing SHA-256 hashes) -- so a
    verified token can't be reused to wave through a different, unverified
    photo,
  * a token is single-use and short-lived.

This is deliberately framed as an integrity/binding layer, not a claim that
the server independently re-verified biometric liveness -- that claim would
be false, since the raw video never reaches it. See services/tourist_id.py
for a similar "the server checks what it truthfully can" pattern.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import logging
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.liveness import LivenessVerification
from app.schemas.liveness import KNOWN_STEPS, LivenessVerifyRequest, LivenessVerifyResponse

logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(minutes=15)
# Below this, the frontend's own step-completion + movement thresholds
# already didn't pass -- this is a final sanity floor, not the primary gate.
MIN_ACCEPTABLE_SCORE = 0.5
MIN_PHOTO_DIMENSION_PX = 120


class _BadPhoto(Exception):
    pass


def _decode_photo(data_uri: str) -> bytes:
    """Real decode-and-sanity-check, not a format sniff. Raises _BadPhoto
    with a tourist-facing reason on anything that isn't a genuine,
    reasonably-sized photo."""
    try:
        header, b64 = data_uri.split(",", 1)
    except ValueError as e:
        raise _BadPhoto("That doesn't look like a captured photo.") from e
    if "image/" not in header:
        raise _BadPhoto("That doesn't look like a captured photo.")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise _BadPhoto("The captured photo could not be read.") from e
    if len(raw) < 500:
        raise _BadPhoto("The captured photo looks empty or corrupted.")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.verify()
        # verify() leaves the file unusable for further reads -- reopen for
        # the dimension check.
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
    except Exception as e:  # noqa: BLE001 -- any Pillow failure means "not a real photo"
        raise _BadPhoto("The captured photo could not be read.") from e
    if w < MIN_PHOTO_DIMENSION_PX or h < MIN_PHOTO_DIMENSION_PX:
        raise _BadPhoto("The captured photo is too small to use.")
    return raw


def verify_liveness(db: Session, payload: LivenessVerifyRequest) -> LivenessVerifyResponse:
    """Record one completed (or abandoned) liveness attempt. Always returns
    a response -- never raises to the caller -- since a demo/browser
    hiccup here must never be a dead end for someone trying to register."""
    try:
        raw = _decode_photo(payload.photo)
    except _BadPhoto as e:
        return LivenessVerifyResponse(
            success=False, verified=False, liveness_score=0.0,
            steps_completed=0, message=str(e),
        )

    steps = [s for s in payload.steps if s in KNOWN_STEPS]
    unique_steps = set(steps)
    steps_completed = len(unique_steps)
    score = max(0.0, min(1.0, payload.liveness_score))

    verified = steps_completed >= len(KNOWN_STEPS) and score >= MIN_ACCEPTABLE_SCORE
    photo_hash = hashlib.sha256(raw).hexdigest()

    token = None
    if verified:
        token = uuid.uuid4().hex
        db.add(LivenessVerification(
            session_id=payload.session_id,
            verification_token=token,
            photo_sha256=photo_hash,
            steps_completed=steps_completed,
            liveness_score=score,
            verified=True,
            expires_at=utc_now() + TOKEN_TTL,
        ))
        db.commit()

    message = (
        "Liveness verification successful." if verified
        else "We couldn't confirm all 3 steps -- please retry in a well-lit, steady position."
    )
    return LivenessVerifyResponse(
        success=True, verified=verified, liveness_score=score,
        steps_completed=steps_completed, message=message, verification_token=token,
    )


def consume_verification(db: Session, token: str, photo_data_uri: str, tourist_id: int) -> bool:
    """Bind a previously-issued verification to the tourist record that was
    actually just created, IF it's still valid and matches the exact photo
    it was issued for. Never raises: a failure here just means the tourist
    is created without the (internal, never publicly exposed) liveness
    stamp -- registration itself always succeeds regardless."""
    row = db.query(LivenessVerification).filter(
        LivenessVerification.verification_token == token
    ).first()
    if row is None or row.consumed or row.expires_at < utc_now():
        return False
    try:
        raw = _decode_photo(photo_data_uri)
    except _BadPhoto:
        return False
    if hashlib.sha256(raw).hexdigest() != row.photo_sha256:
        logger.warning("Liveness token used with a different photo than it was issued for")
        return False
    row.consumed = True
    row.tourist_id = tourist_id
    db.commit()
    return True
