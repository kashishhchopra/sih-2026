"""Digital Tourist Safety ID: the secure QR token behind a tourist's digital
ID card, and the audit trail of every authorized scan against it.

Deliberately separate from the tamper-proof `IdBlock` hash chain (which
anchors the ID's *issuance history*) -- this is the live, revocable
credential a QR code actually carries. See services/tourist_id.py for the
token lifecycle (issue/verify/regenerate) and role-based scan authorization.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.time import utc_now
from app.db.session import Base


class TouristIdToken(Base):
    """One row per issued QR token. Regenerating creates a new row and
    invalidates the old one -- the old token stops verifying immediately,
    same "one active row wins" pattern as PasswordResetToken.
    """
    __tablename__ = "tourist_id_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    # SHA-256 of the raw token embedded in the QR -- only the hash is stored,
    # same reasoning as password_reset.py: whoever holds the database should
    # not thereby be able to use every outstanding QR token.
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    # The raw token, encrypted at rest (same EncryptedString used for
    # document_number) -- verification never reads this column, it always
    # goes through token_hash. This exists only so the *owning tourist* can
    # re-open their own QR later without regenerating (which would invalidate
    # it) every time they view their Digital ID card.
    raw_token_encrypted: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    # active / invalidated (regenerated over, or administratively suspended)
    status: Mapped[str] = mapped_column(String, default="active", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tourist: Mapped["Tourist"] = relationship()  # noqa: F821


class TouristIdScan(Base):
    """One row per authorized QR scan / manual ID lookup -- the structured
    counterpart to the generic AuditLog (services/audit.py also gets a row
    for every scan, so it shows up in the existing Audit Log page too)."""
    __tablename__ = "tourist_id_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int | None] = mapped_column(ForeignKey("tourists.id"), index=True, nullable=True)
    scanner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scanner_role: Mapped[str] = mapped_column(String, default="")
    # qr_token / manual_id -- how the tourist was looked up
    method: Mapped[str] = mapped_column(String, default="qr_token")
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    scan_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    scan_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # verified / invalid / expired / invalidated / not_found
    verification_status: Mapped[str] = mapped_column(String, default="invalid")
    # JSON list of field names actually returned to the scanner -- makes the
    # audit row prove what was (and wasn't) disclosed, not just that a scan happened.
    accessed_fields: Mapped[str] = mapped_column(Text, default="[]")
