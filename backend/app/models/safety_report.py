"""Women & Solo Traveller Safety: a lightweight, always-available text report
-- distinct from a full SOS (services/monitoring.py:trigger_sos), which
stays the one-tap, always-critical emergency path. This is for "I want to
log how I'm feeling about this situation" without necessarily needing a
full dispatch -- real sentiment/distress analysis (services/sentiment.py)
decides whether it escalates into a real Incident+Alert on its own.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class SafetyReport(Base):
    __tablename__ = "safety_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # positive / neutral / negative / fear / anger -- see services/sentiment.py
    sentiment_label: Mapped[str] = mapped_column(String, default="neutral")
    # -1.0 (very negative) .. +1.0 (very positive) -- VADER's compound score.
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    urgency: Mapped[str] = mapped_column(String, default="low")  # low / medium / high
    distress_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set when distress/urgency crossed the threshold and this report opened
    # a real Incident automatically -- see services/sentiment.py:analyze_and_route.
    escalated_incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
