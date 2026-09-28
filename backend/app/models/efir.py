"""Filed E-FIR (First Information Report) records.

`services/efir.generate_efir()` produces a preview dict on demand and is used
by the admin UI before anything is committed. Once an officer actually acts on
it (marking a tourist missing), a persisted EFIR row is what gets filed, PDF'd,
and chained -- the preview and the filed record are deliberately different
things, the way a draft and a submitted form differ.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class EFIR(Base):
    __tablename__ = "efirs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fir_number: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)

    # lifecycle: filed -> closed
    status: Mapped[str] = mapped_column(String, default="filed")

    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    last_known_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_known_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # SHA-256 over the canonical document content, computed at filing time and
    # appended to the tourist's own ID hash chain as an EFIR_FILED block --
    # tying the report to the same tamper-evidence mechanism as the digital ID.
    document_hash: Mapped[str] = mapped_column(String, nullable=False)

    filed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
