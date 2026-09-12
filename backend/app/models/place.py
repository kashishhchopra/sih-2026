"""Nearby-place directory for tourist assistance (pharmacies, transport) --
the categories `PoliceUnit` doesn't already cover (police/ambulance/rescue
already have a real committed OSM import, see services/poi.py). Seeded demo
data by default; `source` says which, exactly like Zone/PoliceUnit already
distinguish "manual" vs "auto"/"osm" data elsewhere in this app.
"""
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PointOfInterest(Base):
    __tablename__ = "points_of_interest"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # category: pharmacy / bus_stop / metro_station / railway_station / taxi_stand
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    phone: Mapped[str] = mapped_column(String, default="")
    # "manual" (seeded demo fixture) or "osm" (real, imported) -- see
    # services/poi.py's fetch_pois.py sibling if this ever grows a live import.
    source: Mapped[str] = mapped_column(String, default="manual")
