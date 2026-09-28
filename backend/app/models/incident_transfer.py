"""Inter-station case transfer records -- the audit trail for handing an
incident from one police station to another (services/police_network.py:
send_case, and the older request/accept/reject trio kept for API
compatibility).

Deliberately its own table rather than reusing IncidentEvent (which already
logs a free-text note on every hand-off): a transfer has real state of its
own -- REQUESTED until a receiving station acts on it, then ACCEPTED or
REJECTED, or ACCEPTED immediately for a direct send_case -- that the
dashboard can query, not just read as history. The live-location session
(EmergencyLocationPing, keyed by incident_id) is untouched by any of this:
a transfer only ever changes Incident.station_id, never which incident owns
the location feed.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class IncidentTransfer(Base):
    __tablename__ = "incident_transfers"
    __table_args__ = (
        Index("ix_incident_transfers_incident_status", "incident_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    from_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("police_stations.id"), nullable=True
    )
    to_station_id: Mapped[int] = mapped_column(ForeignKey("police_stations.id"))
    reason: Mapped[str] = mapped_column(Text, default="")
    # requested -> accepted | rejected | cancelled. No separate "completed"
    # state: acceptance and the station hand-off happen atomically in the
    # same call (see services/police_network.py:accept_transfer), so
    # ACCEPTED already means the case fully belongs to the new station.
    status: Mapped[str] = mapped_column(String, default="requested")
    requested_by: Mapped[str] = mapped_column(String, default="")
    responded_by: Mapped[str | None] = mapped_column(String, nullable=True)
    # Whether the sending station opted to share the live-location feed as
    # part of this hand-off -- purely an audit/UX signal (the dashboard's
    # "View Live Location" quick-link for this transfer): the location
    # session itself is always tied to the incident regardless of this flag
    # (see the module docstring), never gated by it.
    location_shared: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Snapshot of the live-location fix at the moment of the request, so the
    # receiving station can see exactly what was known when the hand-off was
    # proposed even if it later reviews this record long after the case has
    # moved again.
    latest_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    latest_location_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
