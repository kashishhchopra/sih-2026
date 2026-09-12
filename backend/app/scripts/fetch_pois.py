"""One-off: fetch real police stations & hospitals from OpenStreetMap
(Overpass API) around the app's default map center, and write a committed
snapshot at app/data/snapshots/overpass_pois.json.

Not run in CI or at request time -- POIs don't change hourly and Overpass
rate-limits hard, so this is a manual, occasional refresh, not a live feed.
services/poi.py loads the committed output at runtime/seed time.

Usage:
    python -m app.scripts.fetch_pois [--radius-km 15]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from app.core.config import settings

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "overpass_pois.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# amenity=police -> unit_type="police"; amenity=hospital -> unit_type=
# "ambulance" (matches what services/safety_card.py already filters on).
_AMENITY_TO_UNIT_TYPE = {"police": "police", "hospital": "ambulance"}
_DEFAULT_PHONE = {"police": "100", "ambulance": "102"}


def _query(lat: float, lng: float, radius_m: int) -> str:
    return f"""
    [out:json][timeout:60];
    (
      node["amenity"="police"](around:{radius_m},{lat},{lng});
      way["amenity"="police"](around:{radius_m},{lat},{lng});
      node["amenity"="hospital"](around:{radius_m},{lat},{lng});
      way["amenity"="hospital"](around:{radius_m},{lat},{lng});
    );
    out center tags;
    """


def _element_name(tags: dict) -> str | None:
    name = tags.get("name")
    if name:
        return name
    # No name tag is the norm, not the exception, on OSM POIs -- synthesize
    # something usable from an address rather than dropping the point.
    parts = [tags.get("addr:street"), tags.get("addr:city")]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def fetch(lat: float, lng: float, radius_km: float) -> list[dict]:
    resp = httpx.post(
        OVERPASS_URL, data={"data": _query(lat, lng, int(radius_km * 1000))},
        headers={"User-Agent": "smart-tourist-safety/1.0 (dataset build script)"},
        timeout=90,
    )
    resp.raise_for_status()
    elements = resp.json().get("elements", [])

    units = []
    for el in elements:
        tags = el.get("tags", {})
        amenity = tags.get("amenity")
        unit_type = _AMENITY_TO_UNIT_TYPE.get(amenity)
        if unit_type is None:
            continue

        # `out center` puts way coordinates under "center"; nodes have lat/lon
        # directly.
        point = el.get("center") or el
        elat, elng = point.get("lat"), point.get("lon")
        if elat is None or elng is None:
            continue

        name = _element_name(tags) or f"Unnamed {amenity} facility"
        phone = tags.get("phone") or tags.get("contact:phone") or _DEFAULT_PHONE[unit_type]

        units.append({
            "osm_id": el["id"],
            "name": name,
            "unit_type": unit_type,
            "lat": elat,
            "lng": elng,
            "phone": phone,
            "station": name,
        })
    return units


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radius-km", type=float, default=15.0)
    parser.add_argument("--lat", type=float, default=settings.MAP_CENTER_LAT)
    parser.add_argument("--lng", type=float, default=settings.MAP_CENTER_LNG)
    args = parser.parse_args()

    units = fetch(args.lat, args.lng, args.radius_km)
    # Cap to the ~200 nearest so a very dense city doesn't produce an
    # unusably large snapshot or slow down every safety-card/dispatch lookup.
    units = units[:200]

    payload = {
        "_meta": {
            "source": "OpenStreetMap via Overpass API (overpass-api.de)",
            "license": "ODbL -- https://www.openstreetmap.org/copyright",
            "center": [args.lat, args.lng],
            "radius_km": args.radius_km,
            "count": len(units),
        },
        "units": units,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(units)} units)")


if __name__ == "__main__":
    main()
