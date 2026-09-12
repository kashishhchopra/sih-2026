"""Revoked refresh tokens (logout / rotation denylist).

Access tokens are short-lived and are NOT checked against this table on every
request -- that would mean a DB round-trip per API call for a token that
expires in minutes anyway. Refresh tokens are long-lived and are what
actually needs to be revocable, so this only guards the refresh flow: logout
and each refresh-token rotation insert the used token's jti here.
"""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String, primary_key=True)
    # Kept so a periodic cleanup job can drop rows for tokens that would have
    # expired naturally anyway, instead of this table growing forever.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
