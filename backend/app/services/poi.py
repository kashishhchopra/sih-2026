"""Load real police/hospital units from the committed OSM snapshot (see
app/scripts/fetch_pois.py). Runtime lookup lives in services/ so it's
covered by the test suite; the fetch script itself lives in scripts/ and is
excluded (see pyproject.toml) since it needs live network access.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.police import PoliceUnit

logger = logging.getLogger(__name__)

_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "overpass_pois.json"


def load_snapshot() -> list[dict]:
    if not _SNAPSHOT_PATH.exists():
        return []
    with open(_SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f).get("units", [])


def seed_units_from_snapshot(db: Session) -> int:
    """Upsert PoliceUnit rows from the committed OSM snapshot, keyed by
    osm_id so re-running this (e.g. after a fresh `fetch_pois` run) updates
    existing rows instead of duplicating them. Returns the number of units
    written. A missing/empty snapshot writes nothing -- the caller (seed.py)
    falls back to its own hand-written fixtures in that case."""
    units = load_snapshot()
    if not units:
        return 0

    existing = {
        u.osm_id: u for u in db.query(PoliceUnit).filter(PoliceUnit.osm_id.isnot(None)).all()
    }
    written = 0
    for u in units:
        osm_id = u.get("osm_id")
        name = u.get("name")
        lat, lng = u.get("lat"), u.get("lng")
        if osm_id is None or name is None or lat is None or lng is None:
            continue  # malformed snapshot row -- skip rather than crash the seed

        row = existing.get(osm_id)
        if row is None:
            row = PoliceUnit(osm_id=osm_id, source="osm")
            db.add(row)
        row.name = name
        row.station = u.get("station", name)
        row.phone = u.get("phone", "100")
        row.lat = lat
        row.lng = lng
        row.unit_type = u.get("unit_type", "police")
        row.source = "osm"
        written += 1

    if written:
        db.flush()
    return written
