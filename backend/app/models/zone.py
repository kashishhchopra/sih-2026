"""Geo-fenced risk zones defined as polygons."""
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # risk_level: low / medium / high / restricted
    risk_level: Mapped[str] = mapped_column(String, default="medium")
    # polygon: JSON list of [lat, lng] vertices
    polygon: Mapped[str] = mapped_column(Text, nullable=False)
    # mock crime index 0-100 used by the safety-score model
    crime_index: Mapped[float] = mapped_column(Float, default=30.0)
    description: Mapped[str] = mapped_column(Text, default="")
    # auto = discovered by DBSCAN clustering, manual = defined by admin
    source: Mapped[str] = mapped_column(String, default="manual")
    # JSON object mapping hour-of-day (str "0".."23") -> multiplier applied to
    # this zone's base risk weight, e.g. {"20": 1.3, "6": 0.6}. Empty "{}"
    # (the default) means flat behavior -- identical to a zone with no curve.
    time_risk_curve: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    # Indian state/UT this zone is in, if known -- currently informational
    # (no state-wise crime dataset is available, see services/crime_index.py)
    # but keeps the door open for one without another migration.
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    # "manual" (admin hand-set crime_index) or "ncrb" (calibrated from the
    # real national NCRB series via services/crime_index.py). Manual
    # overrides are never touched by the calibration backfill script.
    crime_index_source: Mapped[str] = mapped_column(String, default="manual", server_default="manual")
