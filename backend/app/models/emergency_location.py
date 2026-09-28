"""Live-location pings tied to a specific active SOS/emergency incident --
see services/emergency_location.py.

Deliberately a separate table from LocationPing (the tourist's regular
background tracking stream, used for anomaly detection): that stream keeps
running independent of any emergency, and this one exists ONLY while an
incident's live_tracking_active is True, at a higher, purpose-specific
frequency, carrying fields (accuracy, heading) the regular stream doesn't
need. Keeping them separate means the emergency trail's retention/trimming
policy (see EMERGENCY_LOCATION_TRAIL_MAX_POINTS) never touches the
tourist's ordinary tracking history, and vice versa.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class EmergencyLocationPing(Base):
    __tablename__ = "emergency_location_pings"
    # Every ping looks up the incident's most recent previous ping (for the
    # implied-speed plausibility check) and the dashboard queries "last N for
    # this incident" -- both want this composite index, not a full scan.
    __table_args__ = (
        Index("ix_emergency_pings_incident_timestamp", "incident_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    # Device-reported GPS accuracy radius, metres -- None if the browser
    # didn't supply one. Never fabricated.
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    # Flagged (never auto-escalated -- see the module docstring in
    # services/emergency_location.py) when the implied speed from the
    # previous ping is physically implausible.
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    # True for a clearly-labelled demo/simulated position (see
    # services/emergency_location.py's demo-mode path) -- never presented to
    # police as a real tourist location.
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
