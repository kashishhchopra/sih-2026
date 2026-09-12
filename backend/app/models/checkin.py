"""Tourist Check-in / Check-out: a planned outing the tourist registers ahead
of time (destination + expected return). A miss is treated as a soft distress
signal -- see services/checkin.py:tick_checkins(), which mirrors the
escalation-tick pattern in services/escalation.py.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class CheckIn(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    destination_name: Mapped[str] = mapped_column(String, nullable=False)
    dest_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    dest_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_return_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # planned -> checked_in (on time) | planned -> missed -> escalated (no
    # check-in by the deadline, then a grace period also elapses)
    status: Mapped[str] = mapped_column(String, default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
