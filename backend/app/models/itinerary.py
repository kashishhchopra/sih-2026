"""Uploaded itinerary documents and their extracted trip structure.

Deliberately separate from `Tourist.itinerary` (the existing JSON waypoint
list already used by the map/geofence/AI-copilot code): this table is the
upload -> extract -> tourist-reviews -> confirm workflow's own record, richer
than a waypoint list (hotels, transport, activities, trip dates) and kept
even after confirmation as an audit trail of what was uploaded and what was
actually extracted from it. Confirming writes the destination sequence into
the existing `Tourist.itinerary` field -- see services/itinerary_extract.py.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class ItineraryDocument(Base):
    __tablename__ = "itinerary_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    # pending / extracted / failed -- extraction runs synchronously on
    # upload (documents are small; see settings.ITINERARY_DOCUMENT_MAX_BYTES),
    # so this only ever lands on "extracted" or "failed" by the time the
    # upload response returns.
    status: Mapped[str] = mapped_column(String, default="pending")
    # Why extraction failed, if it did -- shown to the tourist verbatim so
    # "upload didn't work" always has a reason, never a silent dead end.
    error: Mapped[str] = mapped_column(Text, default="")
    # JSON: {trip_dates, destinations[], hotels[], transport[], activities[]}
    # -- the tourist edits this (still JSON) before confirming; see
    # schemas/itinerary.py:ExtractedItinerary for its shape.
    extracted_json: Mapped[str] = mapped_column(Text, default="{}")
    confirmed: Mapped[bool] = mapped_column(default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
