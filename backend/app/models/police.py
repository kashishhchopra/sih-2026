"""Police units, area stations, and CCTV assets for SOS dispatch and
the area-based police network (see services/police_network.py, services/cctv.py)."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class PoliceUnit(Base):
    __tablename__ = "police_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    station: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str] = mapped_column(String, default="100")
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    available: Mapped[bool] = mapped_column(default=True)
    # unit_type: police / ambulance / rescue
    unit_type: Mapped[str] = mapped_column(String, default="police")
    # OpenStreetMap node/way id, set only for units imported by
    # services/poi.py -- lets a re-import upsert instead of duplicating.
    osm_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    # "manual" (hand-written fixture) or "osm" (imported from OpenStreetMap).
    source: Mapped[str] = mapped_column(String, default="manual", server_default="manual")


class PoliceStation(Base):
    """A local police station responsible for one safety zone.

    Every `Zone` is assigned to exactly one station (`zone_id`, unique). An
    SOS raised inside that zone is routed to this station -- see
    `services/police_network.py:assign_station`. Stations are otherwise all
    peers of each other: any one can hand a case to any other via
    `forward_incident`, which is what makes this a *network* rather than a
    fixed hierarchy.
    """
    __tablename__ = "police_stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("zones.id"), unique=True, nullable=True
    )
    phone: Mapped[str] = mapped_column(String, default="100")
    contact_officer: Mapped[str] = mapped_column(String, default="")
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    # Staffing headcount and how many concurrent open cases this station can
    # competently run at once -- the resource signals the fallback system
    # (services/police_network.py:assign_station) checks before routing an
    # incident here. Deliberately generous defaults so a station only
    # actually triggers fallback under real, demonstrable load.
    total_officers: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    max_concurrent_cases: Mapped[int] = mapped_column(Integer, default=5, server_default="5")


class Camera(Base):
    """A CCTV/camera asset positioned inside a zone.

    Started as a directory entry (what camera coverage exists near an
    incident -- see `services/police_network.py:nearby_cameras`). The
    `stream_*` columns below add an optional real video feed on top of that
    directory, without changing what the directory already did: a camera
    with no `stream_url` is still a perfectly valid coverage record, it just
    has no viewable feed.

    Nothing here is ever populated with an invented stream: a URL gets here
    either because an operator registered it (POST /police-network/cameras)
    or because a configured external provider supplied it
    (`services/cctv.py`). LIVE/OFFLINE is never read off `stream_status`
    alone by the API -- it is probed against the real stream and only cached
    here. See `services/cctv.py:camera_status`.
    """
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    # status: active / offline -- the operator's own enable/disable flag for
    # this asset. Deliberately NOT the live connection state (see below).
    status: Mapped[str] = mapped_column(String, default="active")
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # ---- optional real video feed ----
    # Null when this camera is a coverage record with no viewable stream.
    stream_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # hls | mjpeg | webrtc | mp4 | none -- decides which player renders it.
    stream_type: Mapped[str] = mapped_column(
        String, default="none", server_default="none", nullable=False
    )
    # Who the feed comes from, for attribution ("manual" when an operator
    # registered it directly), plus a link to the source's own page.
    feed_source: Mapped[str] = mapped_column(
        String, default="manual", server_default="manual", nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    attribution: Mapped[str | None] = mapped_column(String, nullable=True)
    # Explicit station assignment. Null means "derive it from the zone this
    # camera sits in", which is the existing Zone -> PoliceStation
    # relationship -- so this only ever overrides, never replaces, that.
    assigned_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("police_stations.id"), nullable=True
    )
    # Cached result of the last real reachability probe. Cache only: the API
    # re-probes when it goes stale rather than trusting what is stored here.
    stream_status: Mapped[str | None] = mapped_column(String, nullable=True)
    stream_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
