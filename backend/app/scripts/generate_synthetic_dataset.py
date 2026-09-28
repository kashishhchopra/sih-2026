"""Generate the full synthetic dataset for the Smart Tourist Safety system.

This produces every kind of data the project consumes, in one reproducible run:

  Operational data (loadable into the database)
    zones.csv                 geo-fence polygons + crime index
    police_units.csv          dispatchable units
    tourists.csv              KYC, itinerary, emergency contacts, trip window
    users.csv                 admin + tourist login accounts
    id_chain_events.csv       hash-chain events (hashes are computed at load
                              time -- they are keyed with SECRET_KEY)
    location_pings.csv        the GPS stream (the bulk of the dataset)
    alerts.csv                geofence / anomaly / route_deviation / sos / ...
    incidents.csv             lifecycle records with response timings
    incident_events.csv       per-incident status timeline
    devices.csv               IoT wearables
    device_telemetry.csv      band telemetry incl. heart rate / falls
    efirs.csv                 filed missing-person reports
    audit_logs.csv            security audit trail
    weather_observations.csv  per-day per-location conditions

  ML training data (drop-in replacements for app/ml/generate_data.py)
    ml_movement.csv           IsolationForest  -- 4 features + label
    ml_safety.csv             RandomForest     -- 5 features + target
    ml_incident_points.csv    DBSCAN           -- historical incident lat/lng

  Metadata
    manifest.json             row counts, checksums, generation parameters

Everything is seeded, so two runs with the same arguments produce byte-identical
files -- the evaluation numbers in the report stay stable.

Run:
    python -m app.scripts.generate_synthetic_dataset                 # full (~800k pings)
    python -m app.scripts.generate_synthetic_dataset --profile demo  # small, fast
    python -m app.scripts.generate_synthetic_dataset --tourists 2000 --days 90
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
from contextlib import suppress
from datetime import datetime, timedelta

from app.scripts import synthetic_reference as ref

with suppress(Exception):  # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_OUT = os.path.join("data", "synthetic")

# Profiles trade dataset size against generation time. "full" is the default
# because the point of this dataset is load/soak testing and stable ML metrics;
# "demo" exists so someone can smoke-test the pipeline in a few seconds.
PROFILES = {
    "demo":     {"tourists": 40,   "days": 14, "ml_movement": 6_000,   "ml_safety": 8_000,   "ml_points": 1_500},
    "medium":   {"tourists": 250,  "days": 30, "ml_movement": 40_000,  "ml_safety": 50_000,  "ml_points": 8_000},
    "full":     {"tourists": 750,  "days": 45, "ml_movement": 120_000, "ml_safety": 150_000, "ml_points": 25_000},
    "stress":   {"tourists": 3000, "days": 90, "ml_movement": 400_000, "ml_safety": 500_000, "ml_points": 60_000},
}

EARTH_RADIUS_M = 6_371_000.0
ROUTE_DEVIATION_THRESHOLD_M = 2000.0  # mirrors settings.ROUTE_DEVIATION_THRESHOLD_M
ANOMALY_DEDUPE_MINUTES = 5            # mirrors settings.ANOMALY_INCIDENT_DEDUPE_MINUTES

_RISK_WEIGHT = {"low": 20.0, "medium": 50.0, "high": 80.0, "restricted": 100.0}
_RISK_SEVERITY = {"low": "low", "medium": "medium", "high": "high", "restricted": "critical"}


# --------------------------------------------------------------------------
# Geo helpers (local copies so this tool runs without importing the ORM layer)
# --------------------------------------------------------------------------
def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def min_distance_to_route(lat: float, lng: float, itinerary: list[dict]) -> float:
    """Same explainable proxy the app uses: distance to the nearest waypoint."""
    if not itinerary:
        return 0.0
    return min(haversine_m(lat, lng, w["lat"], w["lng"]) for w in itinerary)


def local_hour(ts: datetime, lng: float) -> int:
    """Solar-offset local hour, matching app/core/time.local_hour_for."""
    return (ts.hour + round(lng / 15.0)) % 24


def mock_weather_risk(lat: float, lng: float) -> float:
    """Byte-for-byte the app's offline weather mock, so a loaded ping's stored
    safety score matches what the running app would recompute for it."""
    return round((abs(lat * 100 + lng * 100) % 60), 1)


# --------------------------------------------------------------------------
# Zones
# --------------------------------------------------------------------------
class ZoneRect:
    """A rectangular geo-fence. The app stores an arbitrary polygon, but every
    zone this generator emits is an axis-aligned rectangle, which makes the
    containment test used during generation exact rather than approximate."""

    __slots__ = ("id", "name", "risk_level", "crime_index", "lat0", "lat1",
                 "lng0", "lng1", "polygon", "description", "source")

    def __init__(self, zid, name, lat, lng, dlat, dlng, risk, crime, desc, source):
        self.id = zid
        self.name = name
        self.risk_level = risk
        self.crime_index = float(crime)
        self.lat0, self.lat1 = lat - dlat, lat + dlat
        self.lng0, self.lng1 = lng - dlng, lng + dlng
        self.polygon = [
            [self.lat0, self.lng0], [self.lat0, self.lng1],
            [self.lat1, self.lng1], [self.lat1, self.lng0],
        ]
        self.description = desc
        self.source = source

    def contains(self, lat: float, lng: float) -> bool:
        return self.lat0 <= lat <= self.lat1 and self.lng0 <= lng <= self.lng1


def build_zones(rng: random.Random) -> list[ZoneRect]:
    zones = [
        ZoneRect(i + 1, name, lat, lng, dlat, dlng, risk, crime, desc, "manual")
        for i, (name, lat, lng, dlat, dlng, risk, crime, desc) in enumerate(ref.ZONE_DEFS)
    ]
    # Auto zones stand in for what DBSCAN discovers from historical incidents:
    # tight clusters around the busiest landmarks, marked source="auto" so the
    # dashboard can distinguish operator-drawn fences from mined ones.
    hotspot_names = [
        "Paltan Bazaar", "Fancy Bazaar", "Kamakhya Temple", "Six Mile",
        "Khanapara", "Jalukbari", "Beltola Bazaar", "Zoo Road Tiniali",
    ]
    by_name = {n: (la, ln) for n, la, ln, _c in ref.LANDMARKS}
    for k, hname in enumerate(hotspot_names):
        la, ln = by_name[hname]
        jitter = rng.uniform(-0.0015, 0.0015)
        zones.append(ZoneRect(
            len(zones) + 1, f"Auto Hot-Zone #{k} (DBSCAN)",
            la + jitter, ln + jitter, 0.0022, 0.0022, "high",
            rng.uniform(58, 74),
            f"Auto-discovered from {rng.randint(45, 320)} historical incidents near {hname}",
            "auto",
        ))
    return zones


def zones_containing(lat: float, lng: float, zones: list[ZoneRect]) -> list[ZoneRect]:
    return [z for z in zones if z.contains(lat, lng)]


# --------------------------------------------------------------------------
# Scoring (mirrors app/services/safety.py + ml_service fallbacks)
# --------------------------------------------------------------------------
def anomaly_verdict(speed_kmh, dist_prev_m, inactivity_min, dist_route_m) -> tuple[bool, float]:
    """The rule the app falls back to when no model is loaded, used here as the
    *label generator*. Training on labels produced by an explicit rule keeps the
    dataset auditable: every positive can be traced to a stated condition."""
    is_anom = speed_kmh > 120 or inactivity_min > 45 or dist_route_m > 3000
    if is_anom:
        # Graded rather than flat, so the score column carries information the
        # IsolationForest's own decision_function can be compared against.
        margin = max(
            speed_kmh / 120.0, inactivity_min / 45.0, dist_route_m / 3000.0,
        )
        return True, round(min(0.99, 0.70 + 0.20 * math.log1p(margin - 1 + 1e-9)), 3)
    load = max(speed_kmh / 120.0, inactivity_min / 45.0, dist_route_m / 3000.0)
    return False, round(0.02 + 0.25 * load, 3)


def safety_score(zone_risk, hour, anomaly_score, crime_index, weather_risk) -> float:
    risk = (
        0.30 * zone_risk
        + 0.25 * anomaly_score * 100
        + 0.25 * crime_index
        + 0.10 * weather_risk
        + 0.10 * (100 if (hour >= 22 or hour <= 5) else 20)
    )
    return round(max(0.0, min(100.0, 100.0 - risk)), 1)


def band_for(score: float) -> str:
    if score >= 75:
        return "safe"
    if score >= 50:
        return "moderate"
    if score >= 25:
        return "risky"
    return "danger"


# --------------------------------------------------------------------------
# Identity / KYC synthesis
# --------------------------------------------------------------------------
def weighted_choice(rng: random.Random, pairs: list[tuple[str, float]]) -> str:
    total = sum(w for _, w in pairs)
    r = rng.uniform(0, total)
    upto = 0.0
    for value, weight in pairs:
        upto += weight
        if r <= upto:
            return value
    return pairs[-1][0]


def make_digital_id(name: str, index: int) -> str:
    """Same shape the API mints (STS- + 12 uppercase hex), but derived from a
    seeded counter so the dataset is reproducible."""
    digest = hashlib.sha256(f"{name}-{index}-synthetic".encode()).hexdigest()[:12].upper()
    return f"STS-{digest}"


def make_document(rng: random.Random, nationality: str) -> tuple[str, str]:
    """Return (document_type, document_number). Aadhaar numbers are emitted
    masked (XXXX-XXXX-nnnn), exactly as the existing seed data does -- there is
    no reason for a test fixture to carry a full 12-digit Aadhaar shape."""
    if nationality == "Indian":
        doc_type = weighted_choice(rng, [("aadhaar", 70), ("passport", 15),
                                         ("voterid", 10), ("pan", 5)])
        if doc_type == "aadhaar":
            return "aadhaar", f"XXXX-XXXX-{rng.randint(1000, 9999)}"
        if doc_type == "voterid":
            letters = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(3))
            return "voterid", f"{letters}{rng.randint(1000000, 9999999)}"
        if doc_type == "pan":
            head = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(5))
            tail = rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
            return "pan", f"{head}{rng.randint(1000, 9999)}{tail}"
    prefix, digits = ref.PASSPORT_FORMATS.get(nationality, ("", 8))
    number = "".join(str(rng.randint(0, 9)) for _ in range(digits))
    return "passport", f"{prefix}{number}"


def make_phone(rng: random.Random, nationality: str) -> str:
    cc, length = ref.PHONE_FORMATS.get(nationality, ("+91", 10))
    # Indian mobile numbers start 6-9; keeping that true avoids a dataset that
    # fails any downstream format validation someone later adds.
    first = rng.choice("6789") if cc == "+91" else str(rng.randint(1, 9))
    rest = "".join(str(rng.randint(0, 9)) for _ in range(length - 1))
    return f"{cc}-{first}{rest}"


def make_name(rng: random.Random, nationality: str) -> str:
    given, family = ref.NAME_POOLS.get(nationality, ref.NAME_POOLS["Indian"])
    return f"{rng.choice(given)} {rng.choice(family)}"


def make_email(rng: random.Random, full_name: str, index: int) -> str:
    slug = full_name.lower().replace(" ", ".").replace("'", "")
    domain = rng.choice(["example.com", "mailbox.test", "traveller.test", "inbox.test"])
    return f"{slug}.{index}@{domain}"


def make_emergency_contacts(rng: random.Random, nationality: str) -> list[dict]:
    n = rng.choices([1, 2, 3, 4], weights=[15, 45, 30, 10])[0]
    contacts = []
    for i in range(n):
        relation = ref.EMERGENCY_RELATIONS[i] if i < 2 else rng.choice(ref.EMERGENCY_RELATIONS)
        if relation == "hotel":
            cname = rng.choice(ref.HOTELS) + " Front Desk"
            phone = make_phone(rng, "Indian")
        elif relation == "embassy" and nationality != "Indian":
            cname = f"{nationality} Consulate, Kolkata"
            phone = make_phone(rng, "Indian")
        else:
            cname = make_name(rng, nationality)
            phone = make_phone(rng, nationality)
        contacts.append({"name": cname, "phone": phone, "relation": relation})
    return contacts


# --------------------------------------------------------------------------
# Trip + movement synthesis
# --------------------------------------------------------------------------
LANDMARK_BY_NAME = {n: (la, ln, cat) for n, la, ln, cat in ref.LANDMARKS}


BASE_GROUP_GAP_M = 12_000   # waypoints further apart than this need a new hotel
VIA_SPACING_M = 2_500       # spacing of "en route" waypoints along a planned leg
MAX_ITINERARY_POINTS = 40   # schema allows 50; leave headroom


def build_itinerary(rng: random.Random) -> tuple[str, list[dict], int]:
    cluster_name, names, dmin, dmax = rng.choice(ref.TRIP_CLUSTERS)
    k = min(len(names), rng.randint(3, 6))
    chosen = rng.sample(names, k)
    waypoints = []
    for nm in chosen:
        la, ln, _cat = LANDMARK_BY_NAME[nm]
        waypoints.append({"name": nm, "lat": round(la, 6), "lng": round(ln, 6)})
    return cluster_name, waypoints, rng.randint(dmin, dmax)


def order_waypoints(waypoints: list[dict]) -> list[dict]:
    """Nearest-neighbour ordering. A tourist visits nearby places on the same
    day; sampling the cluster at random and using that order would produce a
    ping stream that teleports back and forth across the map."""
    remaining = waypoints[1:]
    route = [waypoints[0]]
    while remaining:
        last = route[-1]
        nxt = min(remaining, key=lambda w: haversine_m(last["lat"], last["lng"],
                                                       w["lat"], w["lng"]))
        remaining.remove(nxt)
        route.append(nxt)
    return route


def group_waypoints(route: list[dict]) -> list[list[dict]]:
    """Split an ordered route into base groups -- each group is one hotel's
    worth of day trips. A hop between groups is an inter-city transfer, not a
    walk, and is modelled as a coverage gap rather than a ping stream."""
    groups = [[route[0]]]
    for wp in route[1:]:
        prev = groups[-1][-1]
        if haversine_m(prev["lat"], prev["lng"], wp["lat"], wp["lng"]) <= BASE_GROUP_GAP_M:
            groups[-1].append(wp)
        else:
            groups.append([wp])
    return groups


def build_full_itinerary(groups: list[list[dict]], homes: list[dict]) -> list[dict]:
    """The stored itinerary: destinations, the hotel for each leg of the stay,
    and "en route" points along each planned intra-city leg.

    The via points matter. `min_distance_to_route` measures the distance to the
    nearest *waypoint*, so an itinerary of endpoints alone reports a tourist
    halfway along a legitimate 6 km road as 3 km off-route -- the route-deviation
    alarm would fire on every normal journey. A real planned itinerary names the
    places you pass through, and including them makes the metric mean what the
    application says it means.
    """
    itinerary: list[dict] = []
    for home, group in zip(homes, groups, strict=True):
        itinerary.append(home)
        itinerary.extend(group)

    budget = MAX_ITINERARY_POINTS - len(itinerary)
    if budget <= 0:
        return itinerary[:MAX_ITINERARY_POINTS]

    legs: list[tuple[dict, dict]] = []
    for home, group in zip(homes, groups, strict=True):
        cursor = home
        for wp in group:
            legs.append((cursor, wp))
            cursor = wp
        legs.append((cursor, home))

    scored: list[tuple[float, dict]] = []
    for a, b in legs:
        dist = haversine_m(a["lat"], a["lng"], b["lat"], b["lng"])
        n = int(dist // VIA_SPACING_M)
        for i in range(1, n + 1):
            t = i / (n + 1)
            lat, lng = interpolate((a["lat"], a["lng"]), (b["lat"], b["lng"]), t)
            scored.append((dist, {"name": f"En route to {b['name']}",
                                  "lat": round(lat, 6), "lng": round(lng, 6)}))
    # Longest legs first, so the budget is spent where deviation would otherwise
    # be worst rather than on whichever leg happened to be enumerated first.
    scored.sort(key=lambda s: -s[0])
    return itinerary + [via for _dist, via in scored[:budget]]


def jitter(rng: random.Random, value: float, spread: float) -> float:
    return value + rng.uniform(-spread, spread)


def interpolate(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def make_ping(prev: dict | None, itinerary: list[dict], zones: list[ZoneRect],
              ts: datetime, lat: float, lng: float, speed: float, mode: str,
              scenario: str) -> dict:
    """Build one ping with every derived field the pipeline would compute for it.

    The derivations deliberately duplicate `services/monitoring.process_ping`:
    the dataset is only useful if a loaded row carries the same anomaly verdict
    and safety score the running application would have produced from it.
    """
    if prev is None:
        dist_prev, dt_s = 0.0, 1.0
    else:
        dist_prev = haversine_m(prev["lat"], prev["lng"], lat, lng)
        dt_s = max((ts - prev["ts"]).total_seconds(), 1.0)
    inactivity_min = dt_s / 60.0
    dist_route = min_distance_to_route(lat, lng, itinerary)
    is_anom, a_score = anomaly_verdict(speed, dist_prev, inactivity_min, dist_route)

    inside = zones_containing(lat, lng, zones)
    if inside:
        worst = max(inside, key=lambda z: _RISK_WEIGHT.get(z.risk_level, 50))
        zone_risk = _RISK_WEIGHT.get(worst.risk_level, 50)
        crime_idx = worst.crime_index
    else:
        zone_risk, crime_idx = 15.0, 20.0
    hour = local_hour(ts, lng)
    sscore = safety_score(zone_risk, hour, a_score, crime_idx, mock_weather_risk(lat, lng))

    return {"ts": ts, "lat": lat, "lng": lng, "speed": speed, "dist_prev": dist_prev,
            "inactivity": inactivity_min, "dist_route": dist_route, "is_anom": is_anom,
            "score": a_score, "inside": inside, "safety": sscore, "hour": hour,
            "mode": mode, "scenario": scenario}


def travel_mode(distance_m: float, rng: random.Random) -> tuple[str, float]:
    """Pick a plausible mode and cruise speed for a leg of the given length."""
    if distance_m < 1200:
        return "walk", rng.uniform(3.0, 6.0)
    if distance_m < 15_000:
        return "auto_rickshaw" if rng.random() < 0.45 else "taxi", rng.uniform(18.0, 42.0)
    if distance_m < 80_000:
        return "highway_car", rng.uniform(52.0, 88.0)
    return "long_distance_coach", rng.uniform(45.0, 78.0)


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------
class DatasetWriter:
    """Streams rows to CSV so memory stays flat regardless of dataset size."""

    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self._files: dict[str, object] = {}
        self._writers: dict[str, csv.writer] = {}
        self.counts: dict[str, int] = {}

    def open(self, name: str, header: list[str]) -> None:
        # noqa justification: a context manager cannot express this -- all 17
        # writers stay open for the whole generation pass so rows can be streamed
        # to whichever file they belong to as they are produced. close() below is
        # called from generate()'s finally block.
        f = open(  # noqa: SIM115
            os.path.join(self.out_dir, f"{name}.csv"), "w", newline="", encoding="utf-8")
        self._files[name] = f
        self._writers[name] = csv.writer(f, lineterminator="\n")
        self._writers[name].writerow(header)
        self.counts[name] = 0

    def row(self, name: str, values: list) -> None:
        self._writers[name].writerow(values)
        self.counts[name] += 1

    def close(self) -> None:
        for f in self._files.values():
            f.close()


def iso(ts: datetime) -> str:
    """Naive-UTC ISO string -- the convention every DateTime column here uses."""
    return ts.replace(microsecond=0).isoformat(sep=" ")


def generate(out_dir: str, n_tourists: int, window_days: int, seed: int,
             ml_movement_rows: int, ml_safety_rows: int, ml_point_rows: int,
             now: datetime | None = None) -> dict:
    w = DatasetWriter(out_dir)
    try:
        return _generate(w, out_dir, n_tourists, window_days, seed, ml_movement_rows,
                         ml_safety_rows, ml_point_rows, now)
    finally:
        w.close()


def _generate(w: DatasetWriter, out_dir: str, n_tourists: int, window_days: int,
              seed: int, ml_movement_rows: int, ml_safety_rows: int,
              ml_point_rows: int, now: datetime | None) -> dict:
    rng = random.Random(seed)
    now = now or datetime.utcnow().replace(microsecond=0)

    # ---------------- zones ----------------
    zones = build_zones(rng)
    w.open("zones", ["id", "name", "risk_level", "polygon", "crime_index",
                     "description", "source"])
    for z in zones:
        w.row("zones", [z.id, z.name, z.risk_level, json.dumps(z.polygon),
                        round(z.crime_index, 1), z.description, z.source])

    # ---------------- police units ----------------
    w.open("police_units", ["id", "name", "station", "phone", "lat", "lng", "available"])
    for i, (name, station, phone, lat, lng) in enumerate(ref.POLICE_UNITS, start=1):
        # A few units are mid-callout at snapshot time; the SOS dispatcher must
        # cope with an unavailable nearest unit, so the fixture has to contain some.
        available = rng.random() > 0.15
        w.row("police_units", [i, name, station, phone, lat, lng, int(available)])

    # ---------------- weather observations ----------------
    w.open("weather_observations",
           ["id", "date", "location", "lat", "lng", "condition", "owm_condition_id",
            "temp_c", "wind_speed_ms", "humidity_pct", "rainfall_mm", "weather_risk"])
    weather_by_day: dict[tuple[int, str], float] = {}
    wid = 0
    for day_offset in range(-window_days, 8):
        date = (now + timedelta(days=day_offset)).date()
        monsoon = date.month in ref.MONSOON_MONTHS
        for lname, la, ln, _cat in ref.LANDMARKS:
            if monsoon:
                cond = rng.choices(ref.WEATHER_CONDITIONS,
                                   weights=[3, 5, 6, 8, 9, 12, 12, 9, 6, 8, 5, 6, 5, 4, 1])[0]
            else:
                cond = rng.choices(ref.WEATHER_CONDITIONS,
                                   weights=[22, 18, 14, 10, 4, 4, 3, 1, 1, 2, 1, 6, 6, 7, 1])[0]
            label, owm_id, base_risk = cond
            wind = round(abs(rng.gauss(3.5, 3.0)), 1)
            temp = round(rng.gauss(31 if not monsoon else 28, 5), 1)
            risk = base_risk
            if wind > 15:
                risk += 20
            elif wind > 10:
                risk += 10
            if temp > 42 or temp < 2:
                risk += 15
            risk = round(min(100.0, max(0.0, risk)), 1)
            wid += 1
            w.row("weather_observations", [
                wid, date.isoformat(), lname, la, ln, label, owm_id, temp, wind,
                rng.randint(45, 98), round(max(0.0, rng.gauss(18 if monsoon else 2, 25)), 1),
                risk,
            ])
            weather_by_day[(day_offset, lname)] = risk

    # ---------------- tourists and everything hanging off them ----------------
    w.open("tourists", ["id", "digital_id", "full_name", "nationality", "document_type",
                        "document_number", "phone", "itinerary", "emergency_contacts",
                        "trip_start", "trip_end", "last_lat", "last_lng", "last_seen",
                        "safety_score", "tracking_enabled", "status", "created_at",
                        "behaviour_profile", "trip_cluster"])
    w.open("users", ["id", "email", "full_name", "role", "password", "tourist_id",
                     "created_at"])
    w.open("id_chain_events", ["tourist_id", "index", "event", "data", "timestamp"])
    w.open("location_pings", ["id", "tourist_id", "lat", "lng", "speed_kmh", "timestamp",
                              "anomaly_score", "is_anomaly", "dist_from_prev_m",
                              "inactivity_min", "dist_from_route_m", "in_zone_ids",
                              "safety_score", "band", "travel_mode", "scenario"])
    w.open("alerts", ["id", "tourist_id", "type", "zone_id", "severity", "message",
                      "lat", "lng", "acknowledged", "created_at"])
    w.open("incidents", ["id", "tourist_id", "type", "severity", "status", "description",
                         "lat", "lng", "assigned_unit_id", "detected_at",
                         "acknowledged_at", "dispatched_at", "resolved_at"])
    w.open("incident_events", ["id", "incident_id", "status", "note", "timestamp"])
    w.open("devices", ["id", "device_id", "tourist_id", "api_key", "firmware_version",
                       "battery_pct", "last_heartbeat", "active", "created_at"])
    w.open("device_telemetry", ["id", "device_id", "tourist_id", "lat", "lng", "speed_kmh",
                                "heart_rate_bpm", "battery_pct", "sos_pressed",
                                "fall_detected", "timestamp"])
    w.open("efirs", ["id", "fir_number", "incident_id", "tourist_id", "status",
                     "narrative", "last_known_lat", "last_known_lng", "last_seen_at",
                     "filed_at", "closed_at"])
    w.open("audit_logs", ["id", "timestamp", "actor", "action", "target", "ip",
                          "detail", "outcome"])

    # The admin control-room accounts. Passwords are the demo credentials the
    # README already publishes; the loader hashes them with bcrypt on ingest.
    admin_accounts = [
        ("admin@tourism.gov.in", "Control Room Officer", "admin123"),
        ("dcp.east@guwahatipolice.test", "DCP East District", "admin123"),
        ("dcp.central@guwahatipolice.test", "DCP Central District", "admin123"),
        ("dcp.west@guwahatipolice.test", "DCP West District", "admin123"),
        ("tourism.nodal@assam.gov.test", "Tourism Nodal Officer", "admin123"),
    ]
    user_id = 0
    for email, fname, pwd in admin_accounts:
        user_id += 1
        w.row("users", [user_id, email, fname, "admin", pwd, "",
                        iso(now - timedelta(days=window_days + 30))])

    ping_id = alert_id = incident_id = event_id = device_id_seq = telem_id = 0
    efir_id = audit_id = 0
    movement_samples: list[tuple] = []   # feeds ml_movement.csv
    incident_points: list[tuple] = []    # feeds ml_incident_points.csv
    ips = [f"203.0.113.{i}" for i in range(2, 60)] + [f"198.51.100.{i}" for i in range(2, 60)]

    behaviours = list(ref.BEHAVIOUR_MIX)

    for t_index in range(1, n_tourists + 1):
        nationality = weighted_choice(rng, ref.NATIONALITY_WEIGHTS)
        full_name = make_name(rng, nationality)
        doc_type, doc_number = make_document(rng, nationality)
        cluster_name, destinations, trip_days = build_itinerary(rng)
        route = order_waypoints(destinations)
        groups = group_waypoints(route)
        group_homes = []
        for gi, g in enumerate(groups):
            clat = sum(x["lat"] for x in g) / len(g)
            clng = sum(x["lng"] for x in g) / len(g)
            # Hotels are placed outside high-risk and restricted fences. Without
            # this the accommodation itself sits inside a military perimeter or a
            # night-market fence, and because the app raises a geofence alert per
            # ping with no dedupe, one sleeping tourist would emit an alert every
            # 30 minutes until morning and swamp every other alert type.
            for _ in range(16):
                hlat, hlng = jitter(rng, clat, 0.004), jitter(rng, clng, 0.004)
                if not any(z.risk_level in ("high", "restricted")
                           for z in zones_containing(hlat, hlng, zones)):
                    break
            group_homes.append({"name": f"{rng.choice(ref.HOTELS)} (stay {gi + 1})",
                                "lat": round(hlat, 6), "lng": round(hlng, 6)})
        itinerary = build_full_itinerary(groups, group_homes)
        behaviour = weighted_choice(rng, behaviours)

        # Trips are spread across the whole window, with roughly a fifth still
        # in progress at "now" -- the dashboard must show live and historical
        # tourists side by side, and `is_valid` must be false for expired IDs.
        start_offset = rng.randint(-window_days, 4)
        trip_start = (now + timedelta(days=start_offset)).replace(
            hour=rng.randint(5, 11), minute=rng.choice([0, 15, 30, 45]), second=0)
        trip_end = trip_start + timedelta(days=trip_days, hours=rng.randint(2, 14))

        digital_id = make_digital_id(full_name, t_index)
        contacts = make_emergency_contacts(rng, nationality)
        created_at = trip_start - timedelta(days=rng.randint(0, 21),
                                            hours=rng.randint(0, 23))

        # ---- hash-chain events ----
        chain: list[tuple[str, dict, datetime]] = [
            ("ID_ISSUED", {"digital_id": digital_id, "name": full_name,
                           "document": doc_number, "nationality": nationality,
                           "trip_end": trip_end.isoformat()}, created_at),
            ("KYC_VERIFIED", {"document_type": doc_type, "verified_by": "auto_kyc",
                              "method": "document_scan"},
             created_at + timedelta(minutes=rng.randint(2, 45))),
            ("CHECKIN", {"location": destinations[0]["name"], "lat": destinations[0]["lat"],
                         "lng": destinations[0]["lng"]}, trip_start),
        ]

        # ---- movement simulation ----
        pings: list[dict] = []
        prev: dict | None = None
        scenario_day = rng.randint(0, max(0, trip_days - 1))
        scenario_fired = False
        prev_group = -1

        sim_days = trip_days
        if start_offset + trip_days > 0:  # trip runs past "now": truncate the stream
            sim_days = max(1, min(trip_days, -start_offset + 1))

        for day in range(sim_days):
            day_start = (trip_start + timedelta(days=day)).replace(
                hour=7, minute=rng.randint(0, 59), second=0)
            if day_start > now:
                break
            night_owl = behaviour == "night_wanderer"
            first_hour = 21 if night_owl else 7
            day_start = day_start.replace(hour=first_hour)

            # Days are spread evenly across the base groups; changing group is a
            # hotel-to-hotel transfer (coach/flight) during which the phone is off
            # the network, so it appears as a gap followed by a distant ping --
            # which the anomaly detector legitimately flags and an operator closes
            # as a false positive. That case belongs in the fixture.
            gi = min(len(groups) - 1, day * len(groups) // max(1, sim_days))
            transferred = gi != prev_group and prev_group >= 0
            prev_group = gi
            home = (group_homes[gi]["lat"], group_homes[gi]["lng"])
            if transferred:
                day_start = day_start + timedelta(hours=rng.randint(2, 7))

            targets = rng.sample(groups[gi], min(len(groups[gi]), rng.randint(1, 3)))
            legs: list[tuple[tuple[float, float], tuple[float, float]]] = []
            cursor = home
            for tgt in targets:
                dest = (jitter(rng, tgt["lat"], 0.0012), jitter(rng, tgt["lng"], 0.0012))
                legs.append((cursor, dest))
                cursor = dest
            legs.append((cursor, home))

            ts = day_start
            pings_today = False
            for leg_from, leg_to in legs:
                leg_m = haversine_m(*leg_from, *leg_to)
                mode, cruise = travel_mode(leg_m, rng)
                steps = max(2, min(60, int(leg_m / max(cruise * 1000 / 60 * 4, 120))))
                for s in range(1, steps + 1):
                    frac = s / steps
                    lat, lng = interpolate(leg_from, leg_to, frac)
                    lat = jitter(rng, lat, 0.00035)   # GPS noise, ~30 m
                    lng = jitter(rng, lng, 0.00035)
                    gap_s = rng.randint(150, 420)
                    ts = ts + timedelta(seconds=gap_s)
                    speed = max(0.0, rng.gauss(cruise, cruise * 0.22))
                    scenario_tag = "intercity_transit" if (transferred and not pings_today) \
                        else "normal"
                    pings_today = True

                    # ---- scripted scenario injection ----
                    if (not scenario_fired and day == scenario_day
                            and s == max(1, steps // 2) and behaviour != "normal"):
                        scenario_fired = True
                        scenario_tag = behaviour
                        if behaviour == "route_deviation":
                            lat += rng.choice([-1, 1]) * rng.uniform(0.028, 0.050)
                            lng += rng.choice([-1, 1]) * rng.uniform(0.028, 0.050)
                            speed = rng.uniform(25, 55)
                        elif behaviour == "geofence_intrusion":
                            zone = rng.choice([z for z in zones
                                               if z.risk_level in ("high", "restricted")])
                            lat = rng.uniform(zone.lat0, zone.lat1)
                            lng = rng.uniform(zone.lng0, zone.lng1)
                            speed = rng.uniform(2, 8)
                        elif behaviour == "inactivity":
                            ts = ts + timedelta(minutes=rng.randint(55, 190))
                            speed = rng.uniform(0.0, 0.8)
                        elif behaviour == "high_speed_transit":
                            speed = rng.uniform(92, 118)  # fast but legitimate
                        elif behaviour == "abduction_pattern":
                            lat += rng.choice([-1, 1]) * rng.uniform(0.030, 0.060)
                            lng += rng.choice([-1, 1]) * rng.uniform(0.030, 0.060)
                            speed = rng.uniform(135, 245)
                        elif behaviour in ("sos_panic", "device_fall"):
                            speed = rng.uniform(0.0, 4.0)
                        elif behaviour == "missing_person":
                            speed = rng.uniform(0.0, 2.0)
                        elif behaviour == "night_wanderer":
                            speed = rng.uniform(1.0, 6.0)

                    if ts > now:
                        break

                    p = make_ping(prev, itinerary, zones, ts, lat, lng, speed,
                                  mode, scenario_tag)
                    pings.append(p)
                    prev = p


                # Dwell at the destination. A phone with tracking on keeps
                # reporting while its owner is standing still, so this emits
                # stationary pings rather than a silent gap -- a gap would look
                # like the "prolonged inactivity" scenario to the detector and
                # every ordinary museum visit would raise an alert.
                for _ in range(rng.randint(2, 7)):
                    ts = ts + timedelta(minutes=rng.randint(6, 14))
                    if ts > now:
                        break
                    p = make_ping(prev, itinerary, zones, ts,
                                  jitter(rng, lat, 0.0003), jitter(rng, lng, 0.0003),
                                  rng.uniform(0.0, 1.6), "stationary", "dwell")
                    pings.append(p)
                    prev = p

            # Overnight: a slow heartbeat from the hotel, running from the last
            # ping of the day right through to the next morning. It has to cover
            # the whole night without a hole -- a multi-hour gap is exactly the
            # signature of the "prolonged inactivity" scenario, and leaving one
            # here would mean every tourist raised an anomaly every single night.
            night_ts = ts
            night_end = (day_start + timedelta(days=1)).replace(hour=6, minute=30)
            while night_ts < night_end:
                night_ts = night_ts + timedelta(minutes=rng.randint(20, 40))
                if night_ts > now:
                    break
                p = make_ping(prev, itinerary, zones, night_ts,
                              jitter(rng, home[0], 0.0004), jitter(rng, home[1], 0.0004),
                              rng.uniform(0.0, 0.5), "stationary", "overnight")
                pings.append(p)
                prev = p

        # Sample this tourist's whole stream into the anomaly training set, so
        # ml_movement.csv is drawn from the same process that produced the
        # operational data rather than a separate fiction. Sampling HERE rather
        # than inside the movement loop is the point: dwell and overnight pings
        # are ~84% of real traffic, and a reference distribution built only from
        # moving pings makes /api/ml/drift report significant PSI drift against
        # the very data the model was trained beside.
        for k, p in enumerate(pings):
            if p["is_anom"] or k % 2 == 0:
                movement_samples.append((
                    round(p["speed"], 2), round(p["dist_prev"], 1),
                    round(p["inactivity"], 2), round(p["dist_route"], 1),
                    int(p["is_anom"]), p["scenario"], p["hour"],
                ))

        if not pings:  # trip starts in the future -- registered but not yet travelling
            last_lat, last_lng, last_seen = None, None, None
            final_score = 100.0
        else:
            last = pings[-1]
            last_lat, last_lng, last_seen = last["lat"], last["lng"], last["ts"]
            final_score = last["safety"]

        # ---- derived alerts / incidents ----
        status = "active"
        last_anomaly_incident: datetime | None = None
        tourist_alerts: list[tuple] = []
        escalated_zones: set[int] = set()

        for p in pings:
            if p["is_anom"]:
                if p["speed"] > 120:
                    reason = f"abnormal speed {p['speed']:.0f} km/h (possible vehicle abduction)"
                elif p["inactivity"] > 45:
                    reason = f"prolonged inactivity {p['inactivity']:.0f} min"
                elif p["dist_prev"] > 5000:
                    reason = f"sudden location jump {p['dist_prev']/1000:.1f} km"
                else:
                    reason = "unusual movement pattern"
                alert_id += 1
                w.row("alerts", [alert_id, t_index, "anomaly", "", "high",
                                 f"Anomaly detected: {reason}", round(p["lat"], 6),
                                 round(p["lng"], 6), int(rng.random() < 0.75), iso(p["ts"])])
                tourist_alerts.append(("anomaly", p["ts"], reason))
                if (last_anomaly_incident is None
                        or (p["ts"] - last_anomaly_incident).total_seconds()
                        > ANOMALY_DEDUPE_MINUTES * 60):
                    last_anomaly_incident = p["ts"]
                    incident_id, event_id = _emit_incident(
                        w, rng, incident_id, event_id, t_index, "anomaly", "high",
                        f"AI anomaly: {reason}", p, now)
                    incident_points.append((p["lat"], p["lng"], "anomaly", "high"))

            if itinerary and p["dist_route"] > ROUTE_DEVIATION_THRESHOLD_M:
                alert_id += 1
                w.row("alerts", [alert_id, t_index, "route_deviation", "", "medium",
                                 f"Route deviation: {p['dist_route']/1000:.1f} km from "
                                 "planned itinerary", round(p["lat"], 6),
                                 round(p["lng"], 6), int(rng.random() < 0.6), iso(p["ts"])])
                tourist_alerts.append(("route_deviation", p["ts"], "off itinerary"))

            for z in p["inside"]:
                if z.risk_level not in ("high", "restricted"):
                    continue
                sev = _RISK_SEVERITY.get(z.risk_level, "medium")
                alert_id += 1
                w.row("alerts", [alert_id, t_index, "geofence", z.id, sev,
                                 f"Entered {z.risk_level} risk zone: {z.name}",
                                 round(p["lat"], 6), round(p["lng"], 6),
                                 int(rng.random() < 0.8), iso(p["ts"])])
                tourist_alerts.append(("geofence", p["ts"], z.name))
                # The pipeline raises a geofence *alert* on every ping inside a
                # fence, but only an operator escalation opens an incident --
                # so this fires once per tourist per restricted zone, on entry,
                # rather than once per ping for as long as they stand there.
                if (z.risk_level == "restricted" and z.id not in escalated_zones
                        and rng.random() < 0.5):
                    escalated_zones.add(z.id)
                    incident_id, event_id = _emit_incident(
                        w, rng, incident_id, event_id, t_index, "geofence", "critical",
                        f"Restricted-zone entry: {z.name}", p, now)
                    incident_points.append((p["lat"], p["lng"], "geofence", "critical"))

        # ---- SOS ----
        if behaviour == "sos_panic" and pings:
            p = pings[min(len(pings) - 1, int(len(pings) * 0.7))]
            msg = rng.choice(ref.SOS_MESSAGES)
            alert_id += 1
            w.row("alerts", [alert_id, t_index, "sos", "", "critical",
                             f"SOS from {full_name}", round(p["lat"], 6),
                             round(p["lng"], 6), 1, iso(p["ts"])])
            incident_id, event_id = _emit_incident(
                w, rng, incident_id, event_id, t_index, "sos", "critical",
                f"SOS triggered by {full_name}: {msg}", p, now, force_dispatch=True)
            incident_points.append((p["lat"], p["lng"], "sos", "critical"))
            chain.append(("SOS_TRIGGERED", {"lat": round(p["lat"], 6),
                                            "lng": round(p["lng"], 6), "message": msg},
                          p["ts"]))
            audit_id += 1
            w.row("audit_logs", [audit_id, iso(p["ts"]), f"tourist:{digital_id}",
                                 "sos_triggered", f"tourist:{t_index}", rng.choice(ips),
                                 msg, "success"])
            # Most SOS cases are resolved; a minority are still open at snapshot.
            status = "sos" if rng.random() < 0.25 else "active"

        # ---- missing person + E-FIR ----
        if behaviour == "missing_person" and pings:
            p = pings[-1]
            status = "missing"
            incident_id, event_id = _emit_incident(
                w, rng, incident_id, event_id, t_index, "missing_person", "critical",
                f"{full_name} has not reported a location for over 6 hours", p, now,
                force_dispatch=True, resolve_probability=0.3)
            incident_points.append((p["lat"], p["lng"], "missing_person", "critical"))
            efir_id += 1
            filed_at = p["ts"] + timedelta(hours=rng.randint(4, 12))
            narrative = (
                f"This E-FIR is auto-generated for missing person {full_name} "
                f"(Digital Tourist ID: {digital_id}, {doc_type.upper()} No: {doc_number}). "
                f"The tourist was last seen at coordinates ({p['lat']:.5f}, {p['lng']:.5f}) "
                f"on {p['ts'].isoformat()}. The Smart Tourist Safety system recorded "
                f"{len(tourist_alerts)} anomaly/alert event(s) prior to loss of contact. "
                "Immediate search and rescue is recommended."
            )
            closed = rng.random() < 0.45
            w.row("efirs", [efir_id, f"EFIR/{filed_at.year}/{t_index:05d}", incident_id,
                            t_index, "closed" if closed else "filed", narrative,
                            round(p["lat"], 6), round(p["lng"], 6), iso(p["ts"]),
                            iso(filed_at),
                            iso(filed_at + timedelta(hours=rng.randint(6, 96))) if closed else ""])
            chain.append(("MARKED_MISSING", {"last_lat": round(p["lat"], 6),
                                             "last_lng": round(p["lng"], 6)}, filed_at))
            chain.append(("EFIR_FILED", {"fir_number": f"EFIR/{filed_at.year}/{t_index:05d}"},
                          filed_at))
            audit_id += 1
            w.row("audit_logs", [audit_id, iso(filed_at), "admin@tourism.gov.in",
                                 "tourist_marked_missing", f"tourist:{t_index}",
                                 rng.choice(ips), f"E-FIR filed for {digital_id}", "success"])

        # ---- IoT wearable ----
        # A tourist whose scripted scenario IS a wearable fall must actually own
        # a wearable, otherwise the fall_detected alert path is never exercised
        # by the dataset at all.
        if pings and (behaviour == "device_fall" or rng.random() < 0.35):
            device_id_seq += 1
            band_id = f"BAND-{t_index:05d}-{rng.randint(1000, 9999)}"
            battery = rng.uniform(35, 100)
            w.row("devices", [device_id_seq, band_id, t_index,
                              hashlib.sha256(f"key-{band_id}".encode()).hexdigest()[:32],
                              rng.choice(ref.FIRMWARE_VERSIONS), round(battery, 1),
                              iso(pings[-1]["ts"]), int(rng.random() < 0.9),
                              iso(created_at)])
            # Telemetry mirrors a subset of the phone pings, plus the signals only
            # a band has: heart rate, a fall accelerometer trip, a hardware SOS.
            telemetry_pings = pings[::6]
            scenario_pings = [p for p in pings if p["scenario"] == behaviour]
            for sp in scenario_pings:
                if sp not in telemetry_pings:
                    telemetry_pings.append(sp)
            telemetry_pings.sort(key=lambda p: p["ts"])
            for p in telemetry_pings:
                telem_id += 1
                battery = max(3.0, battery - rng.uniform(0.05, 0.4))
                if behaviour == "device_fall" and p["scenario"] == "device_fall":
                    hr, fall, sos_btn = rng.uniform(165, 205), 1, int(rng.random() < 0.5)
                elif rng.random() < 0.03:
                    hr = rng.choice([rng.uniform(28, 39), rng.uniform(162, 195)])
                    fall, sos_btn = 0, 0
                else:
                    hr, fall, sos_btn = rng.uniform(58, 118), 0, 0
                w.row("device_telemetry", [telem_id, band_id, t_index, round(p["lat"], 6),
                                           round(p["lng"], 6), round(p["speed"], 2),
                                           round(hr, 1), round(battery, 1), sos_btn, fall,
                                           iso(p["ts"])])
                if fall:
                    alert_id += 1
                    w.row("alerts", [alert_id, t_index, "fall_detected", "", "critical",
                                     "Fall detected by wearable device", round(p["lat"], 6),
                                     round(p["lng"], 6), 1, iso(p["ts"])])
                    incident_id, event_id = _emit_incident(
                        w, rng, incident_id, event_id, t_index, "fall_detected", "critical",
                        f"Possible fall detected by {full_name}'s band", p, now,
                        force_dispatch=True)
                    incident_points.append((p["lat"], p["lng"], "fall_detected", "critical"))
                elif not (40 <= hr <= 160):
                    alert_id += 1
                    w.row("alerts", [alert_id, t_index, "health_anomaly", "", "high",
                                     f"Abnormal heart rate: {hr:.0f} bpm", round(p["lat"], 6),
                                     round(p["lng"], 6), int(rng.random() < 0.7),
                                     iso(p["ts"])])

        # ---- write pings ----
        for p in pings:
            ping_id += 1
            w.row("location_pings", [
                ping_id, t_index, round(p["lat"], 6), round(p["lng"], 6),
                round(p["speed"], 2), iso(p["ts"]), p["score"], int(p["is_anom"]),
                round(p["dist_prev"], 1), round(p["inactivity"], 2),
                round(p["dist_route"], 1),
                "|".join(str(z.id) for z in p["inside"]), p["safety"],
                band_for(p["safety"]), p["mode"], p["scenario"],
            ])

        # ---- checkout block for finished trips ----
        if trip_end < now and status == "active":
            chain.append(("CHECKOUT", {"location": itinerary[-1]["name"],
                                       "trip_completed": True}, trip_end))
        for idx, (event, data, ts) in enumerate(chain):
            w.row("id_chain_events", [t_index, idx, event,
                                      json.dumps(data, sort_keys=True, default=str), iso(ts)])

        # ---- tourist row ----
        w.row("tourists", [
            t_index, digital_id, full_name, nationality, doc_type, doc_number,
            make_phone(rng, nationality),
            json.dumps(itinerary), json.dumps(contacts),
            iso(trip_start), iso(trip_end),
            round(last_lat, 6) if last_lat is not None else "",
            round(last_lng, 6) if last_lng is not None else "",
            iso(last_seen) if last_seen else "",
            final_score, int(rng.random() < 0.88), status, iso(created_at),
            behaviour, cluster_name,
        ])

        # ---- login account (most tourists have one) ----
        if rng.random() < 0.85:
            user_id += 1
            w.row("users", [user_id, make_email(rng, full_name, t_index), full_name,
                            "tourist", "tourist123", t_index, iso(created_at)])
            # Login trail: a handful of successes and the occasional failure, which
            # is what makes the audit page and the brute-force rate limiter testable.
            for _ in range(rng.randint(1, 8)):
                audit_id += 1
                at = created_at + timedelta(minutes=rng.randint(1, 60 * 24 * max(1, trip_days)))
                ok = rng.random() < 0.88
                w.row("audit_logs", [audit_id, iso(min(at, now)),
                                     make_email(rng, full_name, t_index),
                                     "login_success" if ok else "login_failure",
                                     "auth", rng.choice(ips),
                                     "" if ok else "bad credentials",
                                     "success" if ok else "failure"])

        audit_id += 1
        w.row("audit_logs", [audit_id, iso(created_at), "self_registration",
                             "tourist_registered", f"tourist:{t_index}", rng.choice(ips),
                             f"digital_id={digital_id} nationality={nationality}", "success"])

        if t_index % 100 == 0:
            print(f"  ... {t_index}/{n_tourists} tourists, {ping_id:,} pings", flush=True)

    # ---- legacy incident register ----
    # The live pipeline only ever opens "high" anomaly incidents and "critical"
    # geofence/SOS/missing ones, so a dataset built purely from it leaves the
    # analytics severity chart with two bars and no low/medium history to plot.
    # These stand for records migrated from the paper register the control room
    # kept before this system, which is where that spread actually comes from.
    for _ in range(int(n_tourists * 1.2)):
        lname, la, ln, _cat = rng.choice(ref.LANDMARKS)
        ts = now - timedelta(seconds=rng.randint(3600, window_days * 86400))
        itype = rng.choices(["anomaly", "geofence", "sos", "missing_person"],
                            weights=[40, 35, 20, 5])[0]
        severity = rng.choices(["low", "medium", "high", "critical"],
                               weights=[25, 40, 25, 10])[0]
        point = {"ts": ts, "lat": jitter(rng, la, 0.004), "lng": jitter(rng, ln, 0.004)}
        incident_id, event_id = _emit_incident(
            w, rng, incident_id, event_id, rng.randint(1, n_tourists), itype, severity,
            f"Legacy register entry: {itype.replace('_', ' ')} reported near {lname}",
            point, now, resolve_probability=0.95)

    # Background admin activity so the audit log is not composed only of
    # tourist-driven rows.
    for _ in range(min(4000, n_tourists * 6)):
        audit_id += 1
        ts = now - timedelta(seconds=rng.randint(0, window_days * 86400))
        actor = rng.choice([a[0] for a in admin_accounts])
        action = rng.choice(ref.AUDIT_ACTIONS)
        w.row("audit_logs", [audit_id, iso(ts), actor, action, rng.choice(
            ["dashboard", "analytics", "incidents", "zones", "audit", "ml"]),
            rng.choice(ips), "", "failure" if rng.random() < 0.04 else "success"])

    w.close()  # flush every operational CSV before the ML pass reads counts

    # ---------------- ML datasets ----------------
    ml_counts = _write_ml_datasets(out_dir, rng, movement_samples, incident_points,
                                   ml_movement_rows, ml_safety_rows, ml_point_rows, zones)
    w.counts.update(ml_counts)

    manifest = _write_manifest(out_dir, w.counts, {
        "seed": seed, "tourists": n_tourists, "window_days": window_days,
        "generated_at": iso(now), "profile_rows": {
            "ml_movement": ml_movement_rows, "ml_safety": ml_safety_rows,
            "ml_incident_points": ml_point_rows,
        },
    })
    return manifest


def _emit_incident(w: DatasetWriter, rng: random.Random, incident_id: int, event_id: int,
                   tourist_id: int, itype: str, severity: str, description: str,
                   p: dict, now: datetime, force_dispatch: bool = False,
                   resolve_probability: float = 0.82) -> tuple[int, int]:
    """Write one incident plus its status timeline.

    Response timings are drawn from a log-normal-ish spread rather than a flat
    range: most control-room acknowledgements are fast and a long tail is slow,
    which is what makes the analytics page's average response time meaningful.
    """
    incident_id += 1
    detected = p["ts"]
    ack = detected + timedelta(seconds=int(rng.lognormvariate(4.6, 0.8)))
    dispatched = ack + timedelta(seconds=int(rng.lognormvariate(4.9, 0.9)))
    resolved = dispatched + timedelta(seconds=int(rng.lognormvariate(6.9, 0.9)))

    unit = rng.randint(1, len(ref.POLICE_UNITS))
    if force_dispatch or rng.random() < 0.7:
        stage = "resolved" if (resolved <= now and rng.random() < resolve_probability) \
            else "dispatched"
    else:
        stage = rng.choices(["detected", "acknowledged", "resolved"],
                            weights=[15, 20, 65])[0]
        if stage == "resolved" and resolved > now:
            stage = "acknowledged"

    ack_s = iso(ack) if stage in ("acknowledged", "dispatched", "resolved") and ack <= now else ""
    disp_s = iso(dispatched) if stage in ("dispatched", "resolved") and dispatched <= now else ""
    res_s = iso(resolved) if stage == "resolved" else ""

    w.row("incidents", [incident_id, tourist_id, itype, severity, stage, description,
                        round(p["lat"], 6), round(p["lng"], 6),
                        unit if disp_s else "", iso(detected), ack_s, disp_s, res_s])

    timeline = [("detected", description, detected)]
    if ack_s:
        timeline.append(("acknowledged", "Acknowledged by control room", ack))
    if disp_s:
        unit_name = ref.POLICE_UNITS[unit - 1][0]
        station = ref.POLICE_UNITS[unit - 1][1]
        timeline.append(("dispatched", f"Auto-dispatched to {unit_name} ({station})",
                         dispatched))
    if res_s:
        timeline.append(("resolved", rng.choice([
            "Tourist located and confirmed safe",
            "False positive - tourist confirmed movement by phone",
            "Escorted out of restricted area, advisory issued",
            "Medical assistance provided on site",
            "Handed over to the tourist's emergency contact",
            "Recovered belongings, FIR registered at the local station",
        ]), resolved))

    for status, note, ts in timeline:
        event_id += 1
        w.row("incident_events", [event_id, incident_id, status, note, iso(ts)])
    return incident_id, event_id


def _write_ml_datasets(out_dir: str, rng: random.Random, movement_samples: list[tuple],
                       incident_points: list[tuple], n_movement: int, n_safety: int,
                       n_points: int, zones: list[ZoneRect]) -> dict[str, int]:
    """Write the three training datasets.

    The movement set is seeded from real simulated pings and then topped up with
    parametric rows, because the simulation alone under-represents the rare
    scenarios: a training set that is 99.5% normal teaches the detector very
    little about the 0.5% that matters.
    """
    counts: dict[str, int] = {}

    # ---- movement / anomaly ----
    path = os.path.join(out_dir, "ml_movement.csv")
    header = ["speed_kmh", "dist_from_prev_m", "inactivity_min", "dist_from_route_m",
              "label", "scenario", "hour"]
    rows: list[tuple] = []
    normals = [r for r in movement_samples if r[4] == 0]
    anomalies = [r for r in movement_samples if r[4] == 1]
    target_anom = int(n_movement * 0.09)   # ~9% contamination, as the trainer expects
    target_norm = n_movement - target_anom

    rows.extend(rng.sample(normals, min(len(normals), target_norm)))
    rows.extend(rng.sample(anomalies, min(len(anomalies), target_anom)))

    # Top up normals: ordinary walking/short-drive behaviour with a deliberate
    # borderline tail (fast cabs, brief rests) so the classes are not perfectly
    # separable and the reported precision/recall stay honest.
    # The top-up keeps the simulation's own stationary/moving split (~5:1). A
    # purely "walking tourist" top-up would skew the reference speed
    # distribution away from live traffic, which is mostly a phone sitting
    # still in a hotel or a museum.
    while sum(1 for r in rows if r[4] == 0) < target_norm:
        if rng.random() < 0.83:      # stationary: dwell / overnight heartbeat
            speed = min(3.0, max(0.0, abs(rng.gauss(0.3, 0.5))))
            dprev = min(400.0, max(0.0, abs(rng.gauss(45, 60))))
            inact = min(45.0, max(0.5, rng.gauss(22, 10)))
            droute = min(2600.0, max(0.0, abs(rng.gauss(300, 350))))
        else:                        # moving: walk / auto / short drive
            speed = min(95.0, max(0.0, rng.gauss(18, 16)))
            dprev = min(2800.0, max(0.0, rng.gauss(400, 500)))
            inact = min(40.0, max(0.0, rng.gauss(5, 4)))
            droute = min(2600.0, max(0.0, rng.gauss(400, 500)))
        rows.append((round(speed, 2), round(dprev, 1), round(inact, 2), round(droute, 1),
                     0, "synthetic_normal", rng.randint(0, 23)))

    scenarios = ["sudden_jump", "prolonged_inactivity", "abduction_speed",
                 "route_abandonment", "signal_loss_return"]
    while sum(1 for r in rows if r[4] == 1) < target_anom:
        kind = rng.choice(scenarios)
        if kind == "sudden_jump":
            v = (min(90.0, max(0.0, rng.gauss(30, 10))),
                 min(20000.0, max(3000.0, rng.gauss(8000, 3000))),
                 min(15.0, max(0.0, rng.gauss(4, 2))),
                 min(12000.0, max(1000.0, rng.gauss(4000, 1500))))
        elif kind == "prolonged_inactivity":
            v = (min(3.0, max(0.0, rng.gauss(0.5, 0.5))),
                 min(80.0, max(0.0, rng.gauss(20, 15))),
                 min(240.0, max(46.0, rng.gauss(80, 30))),
                 min(2000.0, max(0.0, rng.gauss(500, 300))))
        elif kind == "abduction_speed":
            v = (min(280.0, max(121.0, rng.gauss(160, 32))),
                 min(14000.0, max(2000.0, rng.gauss(5500, 2200))),
                 min(8.0, max(0.0, rng.gauss(2, 1))),
                 min(9000.0, max(500.0, rng.gauss(3000, 1500))))
        elif kind == "route_abandonment":
            v = (min(70.0, max(0.0, rng.gauss(18, 12))),
                 min(6000.0, max(200.0, rng.gauss(1500, 900))),
                 min(40.0, max(0.0, rng.gauss(12, 8))),
                 min(30000.0, max(3100.0, rng.gauss(9000, 5000))))
        else:  # signal_loss_return: long gap AND a large jump
            v = (min(120.0, max(0.0, rng.gauss(25, 15))),
                 min(30000.0, max(4000.0, rng.gauss(12000, 6000))),
                 min(300.0, max(46.0, rng.gauss(120, 60))),
                 min(15000.0, max(500.0, rng.gauss(5000, 3000))))
        rows.append((round(v[0], 2), round(v[1], 1), round(v[2], 2), round(v[3], 1),
                     1, kind, rng.randint(0, 23)))

    rng.shuffle(rows)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(header)
        wr.writerows(rows)
    counts["ml_movement"] = len(rows)

    # ---- safety score regression ----
    path = os.path.join(out_dir, "ml_safety.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["zone_risk", "hour", "anomaly_score", "crime_index", "weather_risk",
                     "safety_score"])
        for _ in range(n_safety):
            # Half the rows are drawn from the real zone catalogue rather than a
            # uniform grid, so the regressor sees the risk/crime combinations that
            # actually occur in this deployment as well as the full input space.
            if rng.random() < 0.5:
                z = rng.choice(zones)
                zone_risk = _RISK_WEIGHT[z.risk_level] + rng.uniform(-5, 5)
                crime = max(0.0, min(100.0, z.crime_index + rng.uniform(-6, 6)))
            else:
                zone_risk = rng.uniform(0, 100)
                crime = rng.uniform(0, 100)
            hour = rng.randint(0, 23)
            a_score = rng.betavariate(1.4, 6.0)  # most pings are unremarkable
            weather = rng.uniform(0, 100)
            night = 1.0 if (hour >= 22 or hour <= 5) else 0.0
            risk = (0.30 * zone_risk + 0.25 * a_score * 100 + 0.25 * crime
                    + 0.10 * weather + 0.10 * (night * 100 + (1 - night) * 20))
            score = max(0.0, min(100.0, 100 - risk + rng.gauss(0, 4)))
            wr.writerow([round(zone_risk, 4), hour, round(a_score, 6), round(crime, 4),
                         round(weather, 4), round(score, 4)])
    counts["ml_safety"] = n_safety

    # ---- DBSCAN incident points ----
    # `train_zones.py` clusters with a FIXED eps=0.005 deg (~550 m) and
    # min_samples=12, so this file's density is not a free parameter. Scattered
    # noise laid down thickly enough that an eps-circle holds 12 points stops
    # being noise and clusters on its own -- which is how a 25k-point file ends
    # up yielding 50 "hot zones" and a negative silhouette. The scatter is
    # therefore capped well under that threshold, and the volume goes into the
    # hotspots, which are what the clustering is supposed to recover.
    path = os.path.join(out_dir, "ml_incident_points.csv")
    hotspot_names = ["Paltan Bazaar", "Fancy Bazaar", "Kamakhya Temple", "Six Mile",
                     "Khanapara", "Jalukbari", "Beltola Bazaar", "Zoo Road Tiniali",
                     "Bharalumukh", "Lokhra", "Saraighat Bridge", "Chandmari"]
    by_name = {n: (la, ln) for n, la, ln, _c in ref.LANDMARKS}
    # The map the dashboard renders is Guwahati; an incident 400 km away in
    # Kaziranga is real history but not a city hot-zone candidate.
    gwh_box = (26.05, 26.25, 91.55, 91.90)
    eps_circle_deg2 = math.pi * 0.005 ** 2
    box_deg2 = (gwh_box[1] - gwh_box[0]) * (gwh_box[3] - gwh_box[2])
    max_scatter = int(0.45 * 12 * box_deg2 / eps_circle_deg2)

    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["lat", "lng", "type", "severity"])
        written = 0
        # Real incidents observed during the simulation come first: the clusters
        # DBSCAN discovers are then genuinely derived from this system's own history.
        in_city = [pt for pt in incident_points
                   if gwh_box[0] <= pt[0] <= gwh_box[1] and gwh_box[2] <= pt[1] <= gwh_box[3]]
        for lat, lng, itype, sev in in_city[:int(n_points * 0.25)]:
            wr.writerow([round(lat, 6), round(lng, 6), itype, sev])
            written += 1

        scatter = min(max_scatter, int(n_points * 0.08))
        per_hotspot = max(1, (n_points - written - scatter) // len(hotspot_names))
        for hname in hotspot_names:
            la, ln = by_name[hname]
            for _ in range(per_hotspot):
                wr.writerow([round(rng.gauss(la, 0.0022), 6),
                             round(rng.gauss(ln, 0.0022), 6),
                             rng.choice(["theft", "harassment", "accident", "scam",
                                         "assault", "lost_person"]),
                             rng.choices(["low", "medium", "high", "critical"],
                                         weights=[30, 40, 22, 8])[0]])
                written += 1
        # Sparse scatter: DBSCAN must label these noise, not bridge two hotspots.
        for _ in range(scatter):
            wr.writerow([round(rng.uniform(gwh_box[0], gwh_box[1]), 6),
                         round(rng.uniform(gwh_box[2], gwh_box[3]), 6),
                         rng.choice(["theft", "accident", "lost_person"]),
                         rng.choices(["low", "medium", "high"], weights=[50, 35, 15])[0]])
            written += 1
    counts["ml_incident_points"] = written
    return counts


def _write_manifest(out_dir: str, counts: dict[str, int], params: dict) -> dict:
    """Row counts, byte sizes and SHA-256 per file.

    The checksums are the point: an ML metric reported in the project report is
    only reproducible if the dataset it was measured on can be identified.
    """
    files = []
    for fname in sorted(os.listdir(out_dir)):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(out_dir, fname)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        files.append({
            "file": fname,
            "rows": counts.get(fname[:-4]),
            "bytes": os.path.getsize(path),
            "sha256": h.hexdigest(),
        })
    manifest = {
        "dataset": "Smart Tourist Safety -- synthetic corpus",
        "parameters": params,
        "files": files,
        "total_bytes": sum(f["bytes"] for f in files),
        "total_rows": sum(f["rows"] or 0 for f in files),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="full")
    ap.add_argument("--tourists", type=int, help="override the profile's tourist count")
    ap.add_argument("--days", type=int, help="override the profile's history window (days)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    p = PROFILES[args.profile]
    n_tourists = args.tourists or p["tourists"]
    days = args.days or p["days"]
    # Scale the ML row counts with an explicit --tourists override so the two
    # halves of the dataset stay proportionate.
    scale = n_tourists / p["tourists"]
    print(f"Generating '{args.profile}' dataset -> {args.out}")
    print(f"  tourists={n_tourists}  history={days}d  seed={args.seed}")

    manifest = generate(
        args.out, n_tourists, days, args.seed,
        int(p["ml_movement"] * scale), int(p["ml_safety"] * scale),
        int(p["ml_points"] * scale),
    )

    print("\n=== Dataset written ===")
    for f in manifest["files"]:
        rows = f"{f['rows']:,}" if f["rows"] is not None else "-"
        print(f"  {f['file']:<28} {rows:>12} rows  {f['bytes']/1e6:>8.2f} MB")
    print(f"  {'TOTAL':<28} {manifest['total_rows']:>12,} rows  "
          f"{manifest['total_bytes']/1e6:>8.2f} MB")
    print(f"\nManifest: {os.path.join(args.out, 'manifest.json')}")
    print("Load it with:  python -m app.scripts.load_synthetic_dataset")


if __name__ == "__main__":
    main()
