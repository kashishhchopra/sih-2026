"""Trip Guardian: a read-only, token-based share link a tourist can hand to a
trusted family member -- no account needed on the guardian's side. See
app/api/guardian.py for the public (unauthenticated) endpoint that resolves
a token to live status, and services/monitoring.py for the SOS notification.
"""
import secrets
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base


def _generate_token() -> str:
    return secrets.token_urlsafe(24)


class TripGuardian(Base):
    __tablename__ = "trip_guardians"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    token: Mapped[str] = mapped_column(String, unique=True, index=True, default=_generate_token)
    guardian_name: Mapped[str] = mapped_column(String, nullable=False)
    # Optional -- where an SOS notification would be sent (phone/email). No
    # real delivery backend is assumed; see services/notifications.py.
    guardian_contact: Mapped[str] = mapped_column(String, default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    tourist: Mapped["Tourist"] = relationship()  # noqa: F821
