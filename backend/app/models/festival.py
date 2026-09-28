"""Festival & Local Event Intelligence: a calendar of festivals/fairs/local
events, used both to inform tourists ("what's happening nearby") and to feed
the Crowd & Queue Forecast (a festival window is a real driver of crowding
that pure zone-density counting can't see on its own -- see
services/crowd_forecast.py).
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class Festival(Base):
    __tablename__ = "festivals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # festival / fair / event / religious / cultural
    category: Mapped[str] = mapped_column(String, default="festival", index=True)
    # Indian state/UT this event is associated with -- informational, same
    # spirit as Zone.state.
    state: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    # True for a yearly event whose date repeats (most festivals) -- the
    # service recomputes the *next* occurrence from month/day rather than
    # requiring a fresh row every year. False for a one-off dated event.
    recurring_yearly: Mapped[bool] = mapped_column(default=True)
    # low / medium / high -- how much this event is expected to add to local
    # crowd density, consumed by services/crowd_forecast.py.
    crowd_impact: Mapped[str] = mapped_column(String, default="medium")
    # "manual" (seeded/curated) -- matches Zone/PointOfInterest's source
    # convention; keeps the door open for a real events-API import later.
    source: Mapped[str] = mapped_column(String, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
