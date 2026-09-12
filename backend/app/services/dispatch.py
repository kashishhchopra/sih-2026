"""Ranked emergency-unit dispatch: which available unit(s) should respond, and
roughly how long would they take to get there.

`monitoring.trigger_sos()` uses this internally to pick its single top-choice
unit; `GET /incidents/{id}/dispatch-candidates` exposes the full ranked list
(top pick + backups) for the responder console / admin dispatch panel.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.police import PoliceUnit
from app.services.geo import haversine_m


def rank_units(
    db: Session, lat: float, lng: float, needed_types: list[str] | None = None
) -> list[dict]:
    """Return available units near (lat, lng), nearest first.

    Each entry: {unit_id, name, unit_type, station, distance_km, eta_min, available}.
    `needed_types`, if given, restricts candidates to those `unit_type`s (e.g.
    ["ambulance"] for a medical emergency); omit/None to consider every type.
    """
    q = db.query(PoliceUnit).filter(PoliceUnit.available == True)  # noqa: E712
    if needed_types:
        q = q.filter(PoliceUnit.unit_type.in_(needed_types))
    units = q.all()

    ranked = []
    for u in units:
        distance_m = haversine_m(lat, lng, u.lat, u.lng)
        distance_km = distance_m / 1000
        eta_min = (distance_km / settings.DISPATCH_ASSUMED_SPEED_KMH) * 60
        ranked.append({
            "unit_id": u.id,
            "name": u.name,
            "unit_type": u.unit_type,
            "station": u.station,
            "distance_km": round(distance_km, 2),
            "eta_min": round(eta_min, 1),
            "available": u.available,
        })
    ranked.sort(key=lambda r: r["distance_km"])
    return ranked
