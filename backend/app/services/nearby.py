"""Nearby-resource discovery: hospitals/police (real, from PoliceUnit --
including the committed OSM import, see services/poi.py) and
pharmacies/transport (PointOfInterest). One merged, distance-sorted list per
category, for the tourist app's "Nearby" panel -- the richer sibling of
services/safety_card.py's single-nearest-of-everything offline snapshot.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.place import PointOfInterest
from app.models.police import PoliceUnit
from app.services.geo import haversine_m

# category -> which real/seeded rows satisfy it. hospital/police come from
# PoliceUnit (unit_type); everything else from PointOfInterest (category).
_UNIT_TYPE_FOR = {"hospital": "ambulance", "police": "police"}
_POI_CATEGORIES_FOR = {
    "pharmacy": ["pharmacy"],
    "transport": ["bus_stop", "metro_station", "railway_station", "taxi_stand"],
}


def _maps_directions_url(lat: float, lng: float) -> str:
    """A universal (no API key needed) turn-by-turn navigation deep link --
    opens in the user's own maps app/Google Maps in the browser. This is
    exactly the "navigation/deep-link instead of fake booking" fallback the
    transport-assistance feature calls for."""
    return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"


def find_nearby(db: Session, lat: float, lng: float, category: str, radius_m: float = 5000) -> list[dict]:
    """Every known place of `category` within `radius_m`, nearest first.
    `category`: hospital | police | pharmacy | transport."""
    out: list[dict] = []

    unit_type = _UNIT_TYPE_FOR.get(category)
    if unit_type:
        units = db.query(PoliceUnit).filter(
            PoliceUnit.unit_type == unit_type, PoliceUnit.available.is_(True)
        ).all()
        for u in units:
            dist = haversine_m(lat, lng, u.lat, u.lng)
            if dist <= radius_m:
                out.append({
                    "name": u.name, "category": category, "lat": u.lat, "lng": u.lng,
                    "phone": u.phone, "distance_km": round(dist / 1000, 2),
                    "directions_url": _maps_directions_url(u.lat, u.lng),
                    "source": "osm" if u.osm_id else "manual",
                })

    poi_categories = _POI_CATEGORIES_FOR.get(category)
    if poi_categories:
        places = db.query(PointOfInterest).filter(PointOfInterest.category.in_(poi_categories)).all()
        for p in places:
            dist = haversine_m(lat, lng, p.lat, p.lng)
            if dist <= radius_m:
                out.append({
                    "name": p.name, "category": p.category, "lat": p.lat, "lng": p.lng,
                    "phone": p.phone, "distance_km": round(dist / 1000, 2),
                    "directions_url": _maps_directions_url(p.lat, p.lng),
                    "source": p.source,
                })

    out.sort(key=lambda r: r["distance_km"])
    return out
