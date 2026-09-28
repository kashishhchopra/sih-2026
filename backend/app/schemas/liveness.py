"""Schemas for the registration-time liveness check (app/api/tourists.py's
POST /tourists/verify-liveness). See app/services/liveness.py for what each
field is actually checked against."""
from pydantic import BaseModel, Field

# Matches frontend/src/lib/liveness.js's step ids exactly -- kept as a
# constant here (not re-derived) so a typo on either side fails loudly
# instead of silently under-counting steps.
KNOWN_STEPS = ("turn_right", "look_up", "nod")


class LivenessVerifyRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=80)
    # Same bounds as Tourist.photo (schemas/tourist.py) -- this photo is the
    # exact frame that becomes the profile photo, so it must fit the same
    # limits or registration would reject it later anyway.
    photo: str = Field(..., min_length=10, max_length=2_000_000)
    steps: list[str] = Field(..., min_length=1, max_length=3)
    liveness_score: float = Field(..., ge=0.0, le=1.0)


class LivenessVerifyResponse(BaseModel):
    success: bool
    verified: bool
    liveness_score: float
    steps_completed: int
    message: str
    # Only set when verified=True. Sent back to the client, threaded through
    # as TouristCreate.liveness_token, and consumed at registration time --
    # never a bearer of biometric data itself, just an opaque reference.
    verification_token: str | None = None
