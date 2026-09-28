"""Offline Maps & Safety Card: the essentials that must survive a total loss
of signal -- nearest hospital/police, and local emergency numbers.

This endpoint itself needs nothing offline-specific; the offline-first
behaviour comes from the PWA's existing Workbox `NetworkFirst` GET cache
(see frontend/vite.config.js), which already caches every `/api/*` GET
response for use when the network is unavailable -- this just gives it a
small, cacheable payload worth having on hand. Map *tile* caching lives in
the same Workbox config as a `CacheFirst` rule for OSM tile requests.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.place import PointOfInterest
from app.models.police import PoliceUnit
from app.models.tourist import Tourist
from app.services import consular
from app.services.geo import haversine_m

_TRANSPORT_CATEGORIES = ("bus_stop", "metro_station", "railway_station", "taxi_stand")

# National emergency numbers that work regardless of network/carrier --
# static by design, since this is exactly the information that must be
# available with zero connectivity. India's unified emergency number covers
# every tourist regardless of nationality; the rest are the standard
# category numbers used across India.
EMERGENCY_NUMBERS = {
    "all_in_one": "112",
    "police": "100",
    "fire": "101",
    "ambulance": "102",
    "women_helpline": "1091",
    "tourist_helpline": "1363",
}


def _nearest(tourist: Tourist, units: list[PoliceUnit]) -> dict | None:
    if not units or tourist.last_lat is None:
        return None
    nearest = min(units, key=lambda u: haversine_m(tourist.last_lat, tourist.last_lng, u.lat, u.lng))
    return {
        "name": nearest.name, "station": nearest.station, "phone": nearest.phone,
        "lat": nearest.lat, "lng": nearest.lng,
        "distance_km": round(haversine_m(tourist.last_lat, tourist.last_lng,
                                         nearest.lat, nearest.lng) / 1000, 2),
    }


def _nearest_poi(tourist: Tourist, places: list[PointOfInterest]) -> dict | None:
    if not places or tourist.last_lat is None:
        return None
    nearest = min(places, key=lambda p: haversine_m(tourist.last_lat, tourist.last_lng, p.lat, p.lng))
    return {
        "name": nearest.name, "category": nearest.category, "phone": nearest.phone,
        "lat": nearest.lat, "lng": nearest.lng,
        "distance_km": round(haversine_m(tourist.last_lat, tourist.last_lng,
                                         nearest.lat, nearest.lng) / 1000, 2),
    }


def build_safety_card(db: Session, tourist: Tourist) -> dict:
    all_units = db.query(PoliceUnit).filter(PoliceUnit.available.is_(True)).all()
    hospitals = [u for u in all_units if u.unit_type == "ambulance"]
    police = [u for u in all_units if u.unit_type == "police"]
    pharmacies = db.query(PointOfInterest).filter(PointOfInterest.category == "pharmacy").all()
    transport = db.query(PointOfInterest).filter(PointOfInterest.category.in_(_TRANSPORT_CATEGORIES)).all()

    card = {
        "digital_id": tourist.digital_id,
        "nearest_hospital": _nearest(tourist, hospitals),
        "nearest_police": _nearest(tourist, police),
        "nearest_pharmacy": _nearest_poi(tourist, pharmacies),
        "nearest_transport": _nearest_poi(tourist, transport),
        "emergency_numbers": EMERGENCY_NUMBERS,
        "note": (
            "This card works with no signal once loaded -- your browser caches it "
            "automatically. Distances reflect your last known location before you "
            "went offline."
        ),
    }

    # Consular info only for a recognised foreign nationality -- keeps the
    # cached payload small for the (large majority) Indian-national case,
    # and there is nothing to show an Indian tourist here anyway.
    country_code = consular.normalize_nationality(
        tourist.nationality_code or tourist.nationality
    )
    if country_code and country_code != "IN":
        missions = consular.missions_for(country_code, tourist.last_lat, tourist.last_lng)
        card["consular"] = missions[0] if missions else None
        card["country_guidance"] = consular.guidance_for(country_code)

    return card
