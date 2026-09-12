"""Tourist profile, tamper-proof digital ID hash-chain, and location pings."""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.time import utc_now
from app.db.session import Base


class Tourist(Base):
    __tablename__ = "tourists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    digital_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    # KYC
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    # Free-text demonym/country as typed at registration (e.g. "Japanese",
    # "British") -- kept for display/back-compat. `nationality_code` below is
    # the normalised ISO 3166-1 alpha-2 used to look up embassies/guidance
    # (see services/consular.py::normalize_nationality).
    nationality: Mapped[str] = mapped_column(String, default="Indian")
    nationality_code: Mapped[str | None] = mapped_column(String, nullable=True)
    document_type: Mapped[str] = mapped_column(String, default="aadhaar")  # aadhaar / passport
    # Encrypted at rest -- see app/core/crypto.py. Reads return plaintext.
    document_number: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    # Digital Tourist Safety ID photo, as a data: URI. Not encrypted (unlike
    # document_number) -- a face photo isn't the same class of secret as a
    # government ID number, and the Digital ID card needs to render it directly.
    photo: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Foreign-tourist / visa fields -- all nullable, only populated when
    # document_type == "passport" (enforced in schemas/tourist.py, not here).
    visa_type: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. e-Visa, Tourist, Business
    visa_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    visa_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    passport_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    planned_states: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of state names

    # Trip
    itinerary: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of {name,lat,lng}
    emergency_contacts: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    hotel: Mapped[str | None] = mapped_column(String, nullable=True)
    trip_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    trip_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Live state
    last_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    safety_score: Mapped[float] = mapped_column(Float, default=100.0)
    tracking_enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active / sos / missing

    # Digital Safety Passport: shown to a responder scanning the tourist's QR.
    preferred_language: Mapped[str] = mapped_column(String, default="en", server_default="en")
    # Privacy & Consent Dashboard: how long raw location pings are kept after
    # the trip ends before a scheduled job purges them (see services/privacy.py).
    data_retention_days: Mapped[int] = mapped_column(Integer, default=90, server_default="90")
    # Duress SOS: set by the tourist in-app; entering this PIN instead of the
    # real one raises a silent SOS with no visible confirmation on screen.
    duress_pin_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )

    id_blocks: Mapped[list["IdBlock"]] = relationship(
        back_populates="tourist", cascade="all, delete-orphan"
    )

    @property
    def is_valid(self) -> bool:
        """Digital ID validity is tied to trip duration."""
        now = utc_now()
        return self.trip_start <= now <= self.trip_end


class IdBlock(Base):
    """A block in the tamper-proof SHA-256 hash chain for a tourist's ID record."""

    __tablename__ = "id_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )
    event: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "ID_ISSUED"
    data: Mapped[str] = mapped_column(Text, default="{}")  # JSON payload
    previous_hash: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    # The exact timestamp string that went into the hash. `timestamp` is a
    # DateTime column and does not round-trip byte-identically through every
    # backend, so verification would drift; this stores what was actually hashed.
    hashed_at: Mapped[str] = mapped_column(String, default="", nullable=False)

    tourist: Mapped["Tourist"] = relationship(back_populates="id_blocks")


class LocationPing(Base):
    """Historical GPS ping stream used by anomaly detection."""

    __tablename__ = "location_pings"
    # Every single ping looks up that tourist's most recent previous ping to
    # derive distance/time deltas. Without this composite index that query is a
    # table scan filtered by tourist_id, which degrades linearly as pings pile up.
    __table_args__ = (
        Index("ix_location_pings_tourist_timestamp", "tourist_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    speed_kmh: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, index=True
    )
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(default=False)
