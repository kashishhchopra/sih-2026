"""Voice-guidance navigation: turns the tourist's current position + their
confirmed itinerary (Tourist.itinerary -- the same field the map, geofence,
and AI copilot already read from) into one spoken-friendly instruction
toward their next stop.

Real (Google Directions API, actual turn-by-turn steps) when
`settings.GOOGLE_MAPS_API_KEY` is set; otherwise a straight-line distance +
compass-bearing instruction ("Head northeast for 1.2 km") computed from real
haversine geometry -- an honest simplification, not a guess, and always
carries `demo: bool` so the frontend/voice assistant can say so. This is
deliberately NOT the trajectory-deviation/safety system (services/geo.py's
route-deviation check) -- this is routine "where do I go next" guidance,
independent of that.
"""
from __future__ import annotations

import json
import math

from app.models.tourist import Tourist
from app.services import maps
from app.services.geo import haversine_m

_COMPASS = [
    "north", "north-east", "east", "south-east",
    "south", "south-west", "west", "north-west",
]


def _bearing_compass(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    """Real great-circle initial bearing from (lat1,lng1) to (lat2,lng2),
    bucketed into one of 8 compass directions for natural speech."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lng2 - lng1)
    x = math.sin(dlambda) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
    idx = round(bearing / 45) % 8
    return _COMPASS[idx]


def _next_waypoint(tourist: Tourist) -> dict | None:
    try:
        itinerary = json.loads(tourist.itinerary or "[]")
    except (json.JSONDecodeError, TypeError):
        return None
    for wp in itinerary:
        if wp.get("lat") is not None and wp.get("lng") is not None:
            return wp
    return None


def get_navigation_guidance(tourist: Tourist) -> dict:
    """Voice-assistant-ready guidance toward the tourist's next itinerary
    stop. Returns `has_destination: False` if there's no live location or no
    placeable next stop -- the caller (voice assistant) should just stay
    quiet rather than invent something to say."""
    dest = _next_waypoint(tourist)
    if dest is None or tourist.last_lat is None or tourist.last_lng is None:
        return {"has_destination": False}

    origin_lat, origin_lng = tourist.last_lat, tourist.last_lng
    dest_lat, dest_lng = dest["lat"], dest["lng"]
    name = dest.get("name") or "your next stop"

    route = maps.directions(origin_lat, origin_lng, dest_lat, dest_lng)
    distance_km = route["distance_km"]
    eta_minutes = round(route["duration_min"])
    demo = route["demo"]
    steps = route.get("steps")  # only present with a real Google Directions call

    distance_m = haversine_m(origin_lat, origin_lng, dest_lat, dest_lng)
    if distance_m < 50:
        instruction = f"You have arrived at {name}."
    elif distance_m < 300:
        instruction = f"You're close to {name}, about {round(distance_m)} metres away."
    elif steps:
        # Real turn-by-turn is available -- lead with the very next step
        # rather than a straight-line compass guess.
        instruction = steps[0]
    else:
        compass = _bearing_compass(origin_lat, origin_lng, dest_lat, dest_lng)
        instruction = (
            f"Head {compass} for about {distance_km} kilometres to reach {name}. "
            f"Estimated time: about {eta_minutes} minutes."
        )

    return {
        "has_destination": True,
        "destination_name": name,
        "distance_km": distance_km,
        "distance_m": round(distance_m),
        "eta_minutes": eta_minutes,
        "demo": demo,
        "instruction": instruction,
        "steps": steps,
        "arrived": distance_m < 50,
    }
