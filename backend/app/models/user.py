"""Auth user accounts (police/admin operators and tourist logins)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    # role: "admin" (police/admin dashboard), "tourist", or "responder" (field
    # unit console)
    role: Mapped[str] = mapped_column(String, default="tourist", nullable=False)
    # link to tourist profile when role == tourist
    tourist_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tourists.id"), nullable=True
    )
    # link to the police unit this account represents when role == responder
    unit_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("police_units.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )
    # Token epoch: any refresh/access token issued (iat) before this instant
    # is rejected even if not individually revoked. Bumped on password reset
    # so a reset invalidates every existing session immediately, not just on
    # next natural refresh-token expiry. See app/api/deps.py::get_current_user
    # and app/api/auth.py::refresh/reset_password.
    sessions_valid_from: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
