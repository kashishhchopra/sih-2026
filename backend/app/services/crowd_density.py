"""Crowd Density Detection: treats how many tracked tourists are concentrated
inside a zone as its own kind of risk.

This reads only data the platform already tracks -- live tourist positions and
zone polygons -- so it runs today against the same synthetic tourist
population the simulator (app/scripts/simulate.py) generates, with no new
dataset or external feed required.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.tourist import Tourist
from app.models.zone import Zone
from app.services.geo import point_in_zone

# Thresholds are tuned for a simulated/demo tourist population. A real
# deployment would calibrate these against each zone's physical capacity.
_LOW_MAX = 15
_MEDIUM_MAX = 40


def density_band(count: int) -> str:
    if count > _MEDIUM_MAX:
        return "high"
    if count > _LOW_MAX:
        return "medium"
    return "low"


def zone_density_report(db: Session) -> list[dict]:
    """Per-zone tourist concentration, sorted busiest first."""
    zones = db.query(Zone).all()
    tourists = db.query(Tourist).filter(
        Tourist.tracking_enabled.is_(True),
        Tourist.last_lat.isnot(None),
        Tourist.last_lng.isnot(None),
    ).all()

    report = []
    for z in zones:
        count = sum(1 for t in tourists if point_in_zone(t.last_lat, t.last_lng, z))
        band = density_band(count)
        report.append({
            "zone_id": z.id,
            "zone": z.name,
            "tourist_count": count,
            "density": band,
            "overcrowded": band == "high",
        })
    report.sort(key=lambda r: r["tourist_count"], reverse=True)
    return report
