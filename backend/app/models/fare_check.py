"""Fair Price: an estimated-fare check for local transport (auto-rickshaw,
taxi/cab, bike-taxi) so a tourist can tell whether a quoted price is
reasonable before paying. See services/fare.py for the estimation itself
(distance from services/maps.py's existing directions() adapter x a
configurable, transparent per-km/per-min rate card -- never a single
hardcoded price).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class FareCheck(Base):
    __tablename__ = "fare_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    # auto_rickshaw / taxi / cab / bike_taxi -- see services/fare.py:RATE_CARD
    transport_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pickup_name: Mapped[str] = mapped_column(String, default="")
    pickup_lat: Mapped[float] = mapped_column(Float, nullable=False)
    pickup_lng: Mapped[float] = mapped_column(Float, nullable=False)
    destination_name: Mapped[str] = mapped_column(String, default="")
    destination_lat: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lng: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    duration_min: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_min: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_max: Mapped[float] = mapped_column(Float, nullable=False)
    quoted_fare: Mapped[float] = mapped_column(Float, nullable=False)
    # fair / slightly_high / overpriced / suspicious -- see services/fare.py
    verdict: Mapped[str] = mapped_column(String, nullable=False, index=True)
    percent_diff: Mapped[float] = mapped_column(Float, default=0.0)
    reported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    report_note: Mapped[str] = mapped_column(Text, default="")
    reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
