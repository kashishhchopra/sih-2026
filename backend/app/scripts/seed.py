"""Seed the database with demo users, tourists, zones, police units, incidents.

Run:  python -m app.scripts.seed
Idempotent-ish: drops & recreates all tables for a clean demo each time.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import date, timedelta

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import utc_now
from app.db.session import Base, SessionLocal
from app.models.incident import Incident, IncidentEvent
from app.models.place import PointOfInterest
from app.models.police import Camera, PoliceStation, PoliceUnit
from app.models.tourist import Tourist
from app.models.user import User
from app.models.zone import Zone
from app.services import cctv, hashchain, poi, tourist_id
from app.services.crime_index import calibrate_zone_crime_index

CENTER = (26.1445, 91.7362)  # Guwahati


def _avatar_svg(initials: str, color: str) -> str:
    """A tiny deterministic placeholder "photo" (initials on a colour swatch)
    so the Digital Tourist Safety ID card has something to render for every
    seeded tourist without needing binary image assets in the repo."""
    import base64

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
        f'<rect width="200" height="200" fill="{color}"/>'
        f'<text x="100" y="118" font-size="72" font-family="sans-serif" '
        f'fill="white" text-anchor="middle">{initials}</text></svg>'
    )
    return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"


def _seed_password(env_var: str) -> str:
    """Demo account passwords come from env when set; otherwise a random
    password is generated and printed once. Nothing weak is hardcoded into
    source, which is what actually ends up in a public repo."""
    value = os.environ.get(env_var)
    if value:
        return value
    generated = secrets.token_urlsafe(9)
    print(f"  ({env_var} not set -- generated: {generated})")
    return generated


def _rect(lat, lng, dlat=0.008, dlng=0.008):
    return [
        [lat - dlat, lng - dlng],
        [lat - dlat, lng + dlng],
        [lat + dlat, lng + dlng],
        [lat + dlat, lng - dlng],
    ]


def _reset_data(db) -> None:
    """Delete all rows, keeping the schema intact.

    This used to drop and recreate every table, which bypassed Alembic: the
    tables came back as whatever the models happened to say, while
    `alembic_version` still claimed the old revision. Deleting rows leaves schema
    ownership with the migrations.
    """
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def seed() -> None:
    if settings.is_production and os.environ.get("SEED_FORCE") != "true":
        raise RuntimeError(
            "Refusing to seed a production database with demo accounts. "
            "Set SEED_FORCE=true if this is genuinely intended."
        )

    admin_password = _seed_password("SEED_ADMIN_PASSWORD")
    tourist_password = _seed_password("SEED_TOURIST_PASSWORD")
    responder_password = _seed_password("SEED_RESPONDER_PASSWORD")

    db = SessionLocal()
    _reset_data(db)
    try:
        # ---- admin / police operator account ----
        db.add(User(
            email="admin@tourism.gov.in", full_name="Control Room Officer",
            hashed_password=hash_password(admin_password), role="admin",
        ))

        # ---- zones (mix of manual + DBSCAN-discovered) ----
        # crime_index values below come from calibrate_zone_crime_index(),
        # anchored to the real NCRB national crime-against-foreigners series
        # (see app/services/crime_index.py) rather than hand-picked numbers.
        zones = [
            Zone(name="Riverside Restricted Area", risk_level="restricted", state="Assam",
                 crime_index_source="ncrb",
                 polygon=json.dumps(_rect(26.1800, 91.7700)),
                 crime_index=calibrate_zone_crime_index("restricted"),
                 description="Border/riverbank — entry prohibited after dusk", source="manual",
                 # Low risk multiplier by day, spikes sharply after dusk (hour 18+)
                 # and stays elevated overnight -- demonstrates time-aware zone risk.
                 time_risk_curve=json.dumps({
                     "0": 1.4, "1": 1.4, "2": 1.4, "3": 1.4, "4": 1.3, "5": 1.2,
                     "6": 0.7, "7": 0.6, "8": 0.6, "9": 0.6, "10": 0.6, "11": 0.6,
                     "12": 0.6, "13": 0.6, "14": 0.6, "15": 0.6, "16": 0.7, "17": 0.9,
                     "18": 1.2, "19": 1.3, "20": 1.4, "21": 1.4, "22": 1.4, "23": 1.4,
                 })),
            Zone(name="Old Market High-Risk Zone", risk_level="high", state="Assam",
                 crime_index_source="ncrb",
                 polygon=json.dumps(_rect(26.1650, 91.7500)),
                 crime_index=calibrate_zone_crime_index("high"),
                 description="Pickpocketing & scam hotspot", source="manual",
                 # Busy/well-lit by day, pickpocketing risk climbs in the evening.
                 time_risk_curve=json.dumps({
                     "9": 0.7, "10": 0.7, "11": 0.7, "12": 0.8, "13": 0.8, "14": 0.8,
                     "17": 1.1, "18": 1.2, "19": 1.3, "20": 1.3, "21": 1.2,
                 })),
            Zone(name="Hillside Trek Caution Zone", risk_level="medium", state="Assam",
                 crime_index_source="ncrb",
                 polygon=json.dumps(_rect(26.1250, 91.7150, 0.01, 0.01)),
                 crime_index=calibrate_zone_crime_index("medium"),
                 description="Landslide-prone trekking route", source="manual"),
            Zone(name="City Center Safe Zone", risk_level="low", state="Assam",
                 crime_index_source="ncrb",
                 polygon=json.dumps(_rect(26.1445, 91.7362, 0.006, 0.006)),
                 crime_index=calibrate_zone_crime_index("low"),
                 description="Well-patrolled tourist district", source="manual"),
        ]

        # auto-discovered hot-zones from DBSCAN, if available
        hz_path = os.path.join("ml_models", "hotzones.json")
        if os.path.exists(hz_path):
            with open(hz_path) as f:
                data = json.load(f)
            for c in data.get("clusters", []):
                zones.append(Zone(
                    name=f"Auto Hot-Zone #{c['cluster']} (DBSCAN)",
                    risk_level="high",
                    polygon=json.dumps(c["polygon"]),
                    crime_index=65,
                    description=f"Auto-discovered from {c['size']} historical incidents",
                    source="auto",
                ))
        db.add_all(zones)
        db.flush()
        riverside_zone, market_zone, hillside_zone, city_zone = zones[:4]

        # ---- area-based police network: one station per zone ----
        stations = [
            # Staffing/capacity varies by station -- a district HQ carries far
            # more concurrent cases than a hillside outpost, which is exactly
            # what makes the resource-fallback routing meaningful (see
            # services/police_network.py:assign_station).
            PoliceStation(name="City Central PS", zone_id=city_zone.id, phone="100",
                          contact_officer="Inspector Rina Baruah",
                          lat=26.1450, lng=91.7370,
                          total_officers=32, max_concurrent_cases=8),
            PoliceStation(name="Riverside PS", zone_id=riverside_zone.id, phone="100",
                          contact_officer="Sub-Inspector Manoj Das",
                          lat=26.1750, lng=91.7650,
                          total_officers=22, max_concurrent_cases=5),
            PoliceStation(name="Market PS", zone_id=market_zone.id, phone="100",
                          contact_officer="Inspector Priya Nair",
                          lat=26.1620, lng=91.7480,
                          total_officers=28, max_concurrent_cases=6),
            PoliceStation(name="Hillside Outpost", zone_id=hillside_zone.id, phone="100",
                          contact_officer="Sub-Inspector Tenzin Lepcha",
                          lat=26.1280, lng=91.7180,
                          total_officers=8, max_concurrent_cases=2),
        ]
        db.add_all(stations)

        # ---- CCTV/camera directory ----
        # Real, public traffic-camera JPEGs from Caltrans District 9 (see
        # app/data/snapshots/cctv_caltrans_d9.json, services/cctv.py:seed_cameras_from_snapshot).
        # Genuine live feeds, just not of these Guwahati zones -- there is no
        # real feed for this demo's actual locations, and a URL-less
        # "mock, no video feed" row is honest but not what the CCTV Network
        # dashboard is meant to demo. Falls back to feed-less coverage
        # records (matching the demo's own zones) if the snapshot is ever
        # removed.
        cctv_count = cctv.seed_cameras_from_snapshot(db)
        if cctv_count:
            print(f"  Imported {cctv_count} real Caltrans District 9 traffic cameras")
        else:
            cameras = [
                Camera(label="City Center Market Sq Cam 1", zone_id=city_zone.id,
                      lat=26.1448, lng=91.7365),
                Camera(label="City Center Bus Stand Cam 2", zone_id=city_zone.id,
                      lat=26.1442, lng=91.7358),
                Camera(label="Old Market Main Gate Cam 1", zone_id=market_zone.id,
                      lat=26.1652, lng=91.7502),
                Camera(label="Riverside Ghat Cam 1", zone_id=riverside_zone.id,
                      lat=26.1798, lng=91.7698),
                Camera(label="Hillside Trailhead Cam 1", zone_id=hillside_zone.id,
                      lat=26.1252, lng=91.7152, status="offline"),
            ]
            db.add_all(cameras)

        # ---- pharmacy/transport directory (demo fixtures -- hospitals and
        # police already have a real committed OSM import, see services/poi.py;
        # these two categories don't yet, so this is clearly-labelled seed
        # data, not a claim of live coverage) ----
        places = [
            PointOfInterest(name="City Center Pharmacy", category="pharmacy",
                            lat=26.1449, lng=91.7368, phone="100"),
            PointOfInterest(name="Old Market Medical Store", category="pharmacy",
                            lat=26.1655, lng=91.7495, phone="100"),
            PointOfInterest(name="Guwahati Railway Station", category="railway_station",
                            lat=26.1809, lng=91.7378, phone="139"),
            PointOfInterest(name="Paltan Bazaar Bus Stand", category="bus_stop",
                            lat=26.1833, lng=91.7458),
            PointOfInterest(name="City Center Taxi Stand", category="taxi_stand",
                            lat=26.1452, lng=91.7372),
            PointOfInterest(name="Old Market Auto Stand", category="taxi_stand",
                            lat=26.1648, lng=91.7505),
        ]
        db.add_all(places)

        # ---- Discovery: hidden spots / regional food / homestays (demo
        # fixtures -- `phone` is reused as a short free-text tip for these
        # three categories, see services/discovery.py) ----
        discovery_places = [
            PointOfInterest(name="Sualkuchi Weavers' Lane", category="hidden_gem",
                            lat=26.0930, lng=91.6330,
                            phone="A quiet riverside village of silk weavers -- rarely on tour itineraries."),
            PointOfInterest(name="Deepor Beel Viewpoint", category="hidden_gem",
                            lat=26.1280, lng=91.6560,
                            phone="A wetland bird sanctuary with a quiet sunset viewpoint, minutes from the city."),
            PointOfInterest(name="Chandubi Lake Trail", category="hidden_gem",
                            lat=25.9670, lng=91.3210,
                            phone="A scenic lake formed by an old earthquake, popular for camping, still off most maps."),
            PointOfInterest(name="Paradise Restaurant (Assamese Thali)", category="regional_food",
                            lat=26.1810, lng=91.7460,
                            phone="Try the traditional Assamese thali -- khar, tenga, and duck curry."),
            PointOfInterest(name="Riverside Fish Curry House", category="regional_food",
                            lat=26.1738, lng=91.7610,
                            phone="Known for masor tenga (tangy fish curry) with fresh Brahmaputra fish."),
            PointOfInterest(name="Street Food Corner, Fancy Bazaar", category="regional_food",
                            lat=26.1865, lng=91.7515,
                            phone="Try jolpan (Assamese breakfast): pitha, doi-chira, and laru."),
            PointOfInterest(name="Brahmaputra Homestay", category="homestay",
                            lat=26.1920, lng=91.7420,
                            phone="Family-run homestay with a river view and home-cooked Assamese meals."),
            PointOfInterest(name="Hillside Village Homestay", category="homestay",
                            lat=26.1300, lng=91.7100,
                            phone="A tribal-run homestay on the trekking trail with cultural evenings."),
        ]
        db.add_all(discovery_places)

        # ---- police units ----
        units = [
            PoliceUnit(name="Unit Alpha", station="City Central PS", phone="100",
                       lat=26.1450, lng=91.7370, unit_type="police"),
            PoliceUnit(name="Unit Bravo", station="Riverside PS", phone="100",
                       lat=26.1750, lng=91.7650, unit_type="police"),
            PoliceUnit(name="Unit Charlie", station="Market PS", phone="100",
                       lat=26.1620, lng=91.7480, unit_type="police"),
            PoliceUnit(name="Unit Delta", station="Hillside Outpost", phone="100",
                       lat=26.1280, lng=91.7180, unit_type="police"),
            PoliceUnit(name="Ambulance 1", station="City Hospital", phone="102",
                       lat=26.1470, lng=91.7390, unit_type="ambulance"),
            PoliceUnit(name="Rescue Team 1", station="Fire & Rescue HQ", phone="101",
                       lat=26.1600, lng=91.7550, unit_type="rescue"),
        ]
        db.add_all(units)
        db.flush()
        responder_unit = units[0]

        # Additionally import real police stations & hospitals from the
        # committed OSM snapshot (app/scripts/fetch_pois.py), if present --
        # augments rather than replaces the hand-written units above so the
        # responder-linked "Unit Alpha" demo flow keeps working exactly as
        # before, while the map also shows genuine coverage across the area.
        osm_count = poi.seed_units_from_snapshot(db)
        if osm_count:
            print(f"  Imported {osm_count} real police/hospital units from OpenStreetMap")

        # ---- responder (field unit) account, linked to Unit Alpha ----
        db.add(User(
            email="responder@tourism.gov.in", full_name="Unit Alpha Responder",
            hashed_password=hash_password(responder_password), role="responder",
            unit_id=responder_unit.id,
        ))

        # ---- demo tourists ----
        now = utc_now()
        demo = [
            {
                "full_name": "Aarav Sharma", "doc": "XXXX-XXXX-4521", "phone": "+91-98765-43210",
                "start": (26.1445, 91.7362), "email": "aarav@example.com",
                "hotel": "City Center Residency",
                "itin": [("Kamakhya Temple", 26.1665, 91.7055),
                         ("City Center", 26.1445, 91.7362),
                         ("Umananda Island", 26.1970, 91.7450)],
            },
            {
                "full_name": "Emma Watson", "doc": "P1234567", "phone": "+44-7700-900123",
                "start": (26.1500, 91.7400), "email": "emma@example.com", "nat": "British",
                "doctype": "passport", "hotel": "Old Market Heritage Inn",
                "itin": [("City Center", 26.1445, 91.7362),
                         ("Old Market", 26.1650, 91.7500)],
            },
            {
                "full_name": "Rohan Verma", "doc": "XXXX-XXXX-8890", "phone": "+91-99887-76655",
                "start": (26.1280, 91.7200), "email": "rohan@example.com",
                "hotel": "Hillside Trekkers Lodge",
                "itin": [("Hillside Trek Start", 26.1250, 91.7150),
                         ("Viewpoint", 26.1200, 91.7100)],
            },
            {
                "full_name": "Sofia Rossi", "doc": "YA9988776", "phone": "+39-333-1234567",
                "start": (26.1600, 91.7480), "email": "sofia@example.com", "nat": "Italian",
                "doctype": "passport", "hotel": "Old Market Heritage Inn",
                "itin": [("Old Market", 26.1650, 91.7500),
                         ("Riverside Walk", 26.1780, 91.7680)],
            },
            {
                "full_name": "Kenji Tanaka", "doc": "TK5544332", "phone": "+81-90-1234-5678",
                "start": (26.1420, 91.7340), "email": "kenji@example.com", "nat": "Japanese",
                "doctype": "passport", "hotel": "City Center Residency",
                "itin": [("City Center", 26.1445, 91.7362),
                         ("Kamakhya Temple", 26.1665, 91.7055)],
            },
        ]
        _avatar_colors = ["#0ea5e9", "#f97316", "#16a34a", "#7c3aed", "#dc2626"]

        for i, d in enumerate(demo):
            slat, slng = d["start"]
            t = Tourist(
                digital_id=f"STS-DEMO{i+1:03d}",
                full_name=d["full_name"],
                nationality=d.get("nat", "Indian"),
                document_type=d.get("doctype", "aadhaar"),
                document_number=d["doc"],
                phone=d["phone"],
                photo=_avatar_svg(
                    "".join(w[0] for w in d["full_name"].split()[:2]).upper(),
                    _avatar_colors[i % len(_avatar_colors)],
                ),
                hotel=d.get("hotel"),
                itinerary=json.dumps([{"name": n, "lat": la, "lng": ln} for n, la, ln in d["itin"]]),
                emergency_contacts=json.dumps([
                    {"name": "Family Contact", "phone": "+91-90000-00000", "relation": "family"},
                    {"name": "Hotel Desk", "phone": "+91-91111-11111", "relation": "hotel"},
                ]),
                trip_start=now - timedelta(days=1),
                trip_end=now + timedelta(days=6),
                last_lat=slat, last_lng=slng, last_seen=now,
                safety_score=90.0, status="active",
            )
            db.add(t)
            db.flush()
            hashchain.append_block(db, t, "ID_ISSUED", {
                "digital_id": t.digital_id, "name": t.full_name, "document": t.document_number,
            })
            hashchain.append_block(db, t, "CHECKIN", {"location": "Arrival", "lat": slat, "lng": slng})
            tourist_id.issue_token(db, t)  # Digital Tourist Safety ID QR token
            # tourist login account
            db.add(User(
                email=d["email"], full_name=d["full_name"],
                hashed_password=hash_password(tourist_password),
                role="tourist", tourist_id=t.id,
            ))

        # ---- a couple of historical resolved incidents (for analytics charts) ----
        t1 = db.query(Tourist).first()
        for days_ago, sev in [(3, "high"), (2, "medium"), (1, "critical")]:
            det = now - timedelta(days=days_ago)
            inc = Incident(
                tourist_id=t1.id, type="anomaly", severity=sev, status="resolved",
                description="Historical resolved incident (seed)",
                lat=t1.last_lat, lng=t1.last_lng,
                detected_at=det, acknowledged_at=det + timedelta(minutes=2),
                dispatched_at=det + timedelta(minutes=5),
                resolved_at=det + timedelta(minutes=20),
            )
            db.add(inc)
            db.flush()
            db.add(IncidentEvent(incident_id=inc.id, status="resolved", note="Closed"))

        # ---- Festival & Local Event Intelligence: a curated calendar (real,
        # well-known Indian festivals/fairs -- month/day only matters since
        # these are `recurring_yearly`, see services/festival.py) ----
        from app.models.festival import Festival

        festivals = [
            Festival(name="Bihu (Rongali)", description="Assam's spring harvest festival with folk dance and music.",
                     category="festival", state="Assam", lat=26.1445, lng=91.7362,
                     start_date=date(now.year, 4, 14), end_date=date(now.year, 4, 20),
                     recurring_yearly=True, crowd_impact="high"),
            Festival(name="Ambubachi Mela", description="Major religious fair at Kamakhya Temple.",
                     category="religious", state="Assam", lat=26.1665, lng=91.7055,
                     start_date=date(now.year, 6, 22), end_date=date(now.year, 6, 26),
                     recurring_yearly=True, crowd_impact="high"),
            Festival(name="Durga Puja", description="Major pan-India festival with elaborate pandals.",
                     category="religious", state="Assam", lat=26.1600, lng=91.7500,
                     start_date=date(now.year, 10, 10), end_date=date(now.year, 10, 14),
                     recurring_yearly=True, crowd_impact="high"),
            Festival(name="Diwali", description="Festival of lights, celebrated nationwide.",
                     category="festival", state=None, lat=None, lng=None,
                     start_date=date(now.year, 11, 1), end_date=date(now.year, 11, 3),
                     recurring_yearly=True, crowd_impact="high"),
            Festival(name="Jonbeel Mela", description="Historic barter-trade fair near Jagiroad, Assam.",
                     category="fair", state="Assam", lat=26.0270, lng=92.2000,
                     start_date=date(now.year, 1, 15), end_date=date(now.year, 1, 17),
                     recurring_yearly=True, crowd_impact="medium"),
            Festival(name="Guwahati Winter Craft Fair", description="Local handicrafts and food stalls.",
                     category="fair", state="Assam", lat=26.1500, lng=91.7400,
                     start_date=date(now.year, 12, 15), end_date=date(now.year, 12, 22),
                     recurring_yearly=True, crowd_impact="medium"),
        ]
        db.add_all(festivals)

        db.commit()
        print("Seed complete.")
        print(f"  Admin login : admin@tourism.gov.in / {admin_password}")
        print(f"  Tourist login: aarav@example.com / {tourist_password} (and emma/rohan/sofia/kenji)")
        print(f"  Responder login: responder@tourism.gov.in / {responder_password} (Unit Alpha)")
        print(f"  Tourists: {db.query(Tourist).count()}, Zones: {db.query(Zone).count()}, "
              f"Units: {db.query(PoliceUnit).count()}, Stations: {db.query(PoliceStation).count()}, "
              f"Cameras: {db.query(Camera).count()}, Places: {db.query(PointOfInterest).count()}, "
              f"Festivals: {db.query(Festival).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
