"""Disaster & Weather Alert Feeds: area-level hazard advisories (flood,
landslide, earthquake, storm) scoped to a zone, distinct from the per-tourist
weather risk factor in services/weather.py. See services/disaster.py.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utc_now
from app.db.session import Base


class DisasterAdvisory(Base):
    __tablename__ = "disaster_advisories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"), index=True)
    # hazard_type: flood / landslide / earthquake / storm
    hazard_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, default="medium")  # low/medium/high/critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String, default="simulated")  # simulated / real feed name
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # CAP <identifier> for a real-feed advisory (see services/cap.py) -- lets
    # tick_disaster_feed dedupe across ticks by the provider's own id rather
    # than only (zone_id, hazard_type), which the simulator still uses.
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # CAP <areaDesc>, the human-readable area the provider described --
    # kept alongside the zone_id match for transparency about what the
    # source actually said vs. which local zone we mapped it onto.
    area_desc: Mapped[str | None] = mapped_column(String, nullable=True)

    # Short display title ("Storm Advisory") and what-to-do safety guidance,
    # both derived deterministically from hazard_type (see
    # services/disaster.py::_title_for/_instructions_for) -- nullable so
    # rows created before this existed just render without them.
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The affected zone's polygon centroid, for map pin placement and as the
    # point the real weather-condition detector actually sampled -- not a
    # precise hazard epicenter. Nullable for the same reason as above.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    zone: Mapped["Zone"] = relationship(viewonly=True)

    @property
    def zone_name(self) -> str | None:
        return self.zone.name if self.zone else None
