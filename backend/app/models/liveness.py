"""Audit record for the tourist-registration 3-step liveness check
(app/services/liveness.py, app/api/tourists.py's POST /verify-liveness).

This table exists purely to bind a browser-side liveness result to the exact
photo that gets stored on the Tourist row -- it never stores a copy of the
photo itself (only its SHA-256), and it never becomes a second source of
truth for the profile picture. `Tourist.photo` (see app/models/tourist.py)
stays the one place the actual image lives, exactly as before this feature
was added.

A row is created when the frontend finishes the 3-step check, and consumed
(matched + marked used) when the tourist actually submits registration --
see `services.liveness.consume_verification`. A token that's never consumed
just expires; nothing about registration depends on this table succeeding,
because a camera/browser limitation must never be able to block someone
from getting a Digital Tourist Safety ID.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class LivenessVerification(Base):
    __tablename__ = "liveness_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    verification_token: Mapped[str] = mapped_column(String, unique=True, index=True)
    # SHA-256 of the exact captured-photo bytes, not the bytes themselves --
    # registration later re-hashes the submitted photo and compares, so a
    # different image can't be swapped in under a verified token.
    photo_sha256: Mapped[str] = mapped_column(String)
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    liveness_score: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set once the tourist record this verification was used for exists --
    # nullable because a verification can (and often will) expire unused.
    tourist_id: Mapped[int | None] = mapped_column(ForeignKey("tourists.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
