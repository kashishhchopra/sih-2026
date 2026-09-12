"""Permit / E-Pass Automation: auto-drafted applications for the permits
some Indian regions require (Inner Line Permit, Protected/Restricted Area
Permit, forest/wildlife entry) -- pre-filled from the tourist's own KYC +
itinerary (see services/permit.py) so the tourist edits and confirms rather
than retyping a government form from scratch.

There's no real government e-pass backend to submit to here (same honesty
rule this project applies everywhere else -- see services/translation.py's
docstring): "confirming" an application only locks in what the tourist
reviewed, tagged with a local tracking id, and hands back the real official
portal URL for them to finish the actual submission themselves -- never
auto-submitted, never presented as a government approval.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class Permit(Base):
    __tablename__ = "permits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    # inner_line_permit / restricted_area_permit / protected_area_permit /
    # forest_entry_permit / wildlife_sanctuary_permit -- see
    # services/permit.py:PERMIT_TYPES for the full catalogue.
    permit_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    destination_name: Mapped[str] = mapped_column(String, default="")
    # JSON: the pre-filled application form (name, nationality, document
    # type, phone, trip dates, destination, purpose) -- editable by the
    # tourist before submission, same "pre-fill then confirm" shape as
    # ExtractedItinerary in models/itinerary.py.
    form_json: Mapped[str] = mapped_column(Text, default="{}")
    # draft (pre-filled, editable) -> reviewed (tourist explicitly confirmed;
    # `reference_no` is a LOCAL tracking id from that point on, never a
    # government-issued number -- the tourist still finishes the real
    # application on the official portal named in services/permit.py).
    status: Mapped[str] = mapped_column(String, default="draft", index=True)
    reference_no: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
