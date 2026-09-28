"""Load the generated synthetic dataset into the application database.

Reads the CSVs written by `app.scripts.generate_synthetic_dataset` and inserts
them through the real SQLAlchemy models, so everything the running application
reads -- encrypted document numbers, bcrypt password hashes, verifiable ID hash
chains, foreign keys -- is genuinely correct rather than raw rows shovelled in.

Run:
    python -m app.scripts.generate_synthetic_dataset      # write data/synthetic/
    python -m app.scripts.load_synthetic_dataset          # then load it

    python -m app.scripts.load_synthetic_dataset --in data/synthetic --keep-existing
    python -m app.scripts.load_synthetic_dataset --limit-pings 100000   # faster demo

Notes
  - The table contents are replaced by default (schema untouched, so Alembic
    still owns it). Pass --keep-existing to append instead.
  - Passwords and device keys are hashed at load time; bcrypt is deliberately
    slow, so distinct passwords are hashed once and reused across accounts that
    share them. Every demo account uses the credentials the README publishes.
  - Hash-chain digests are keyed with SECRET_KEY, which is why they are computed
    here rather than baked into the CSV: a chain generated under one key would
    fail verification under another.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from contextlib import suppress
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import Base, SessionLocal
from app.models.alert import Alert
from app.models.audit import AuditLog
from app.models.device import Device
from app.models.efir import EFIR
from app.models.incident import Incident, IncidentEvent
from app.models.police import PoliceUnit
from app.models.tourist import IdBlock, LocationPing, Tourist
from app.models.user import User
from app.models.zone import Zone
from app.services import hashchain

with suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_IN = os.path.join("data", "synthetic")
BATCH = 5000


def rows(in_dir: str, name: str):
    path = os.path.join(in_dir, f"{name}.csv")
    if not os.path.exists(path):
        return
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def dt(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def num(value: str) -> float | None:
    return float(value) if value not in ("", None) else None


def flag(value: str) -> bool:
    return value in ("1", "true", "True")


def _reset(db: Session) -> None:
    """Delete rows, keep the schema -- migrations own the schema, not this script."""
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def _chain_block(index: int, event: str, data: str, previous_hash: str,
                 hashed_at: str) -> tuple[str, str]:
    """Compute a block digest for a *historical* timestamp.

    `hashchain.append_block` stamps the current time, which would give every
    block in a six-week backfill the same instant. Verification hashes over
    `hashed_at`, so passing the real timestamp through keeps the chain both
    historically accurate and verifiable by the unmodified verifier.
    """
    return hashchain._compute_hash(index, hashed_at, event, data, previous_hash), hashed_at


def load(in_dir: str, keep_existing: bool, limit_pings: int | None) -> dict[str, int]:
    db = SessionLocal()
    counts: dict[str, int] = {}
    try:
        if not keep_existing:
            print("Clearing existing rows...")
            _reset(db)

        # ---------------- zones ----------------
        zones = [
            Zone(id=int(r["id"]), name=r["name"], risk_level=r["risk_level"],
                 polygon=r["polygon"], crime_index=float(r["crime_index"]),
                 description=r["description"], source=r["source"])
            for r in rows(in_dir, "zones")
        ]
        db.add_all(zones)
        counts["zones"] = len(zones)

        # ---------------- police units ----------------
        units = [
            PoliceUnit(id=int(r["id"]), name=r["name"], station=r["station"],
                       phone=r["phone"], lat=float(r["lat"]), lng=float(r["lng"]),
                       available=flag(r["available"]))
            for r in rows(in_dir, "police_units")
        ]
        db.add_all(units)
        counts["police_units"] = len(units)
        db.commit()
        print(f"  zones={counts['zones']}  police_units={counts['police_units']}")

        # ---------------- tourists ----------------
        n = 0
        for r in rows(in_dir, "tourists"):
            db.add(Tourist(
                id=int(r["id"]), digital_id=r["digital_id"], full_name=r["full_name"],
                nationality=r["nationality"], document_type=r["document_type"],
                document_number=r["document_number"], phone=r["phone"],
                itinerary=r["itinerary"], emergency_contacts=r["emergency_contacts"],
                trip_start=dt(r["trip_start"]), trip_end=dt(r["trip_end"]),
                last_lat=num(r["last_lat"]), last_lng=num(r["last_lng"]),
                last_seen=dt(r["last_seen"]), safety_score=float(r["safety_score"]),
                tracking_enabled=flag(r["tracking_enabled"]), status=r["status"],
                created_at=dt(r["created_at"]),
            ))
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["tourists"] = n
        print(f"  tourists={n}")

        # ---------------- users ----------------
        # bcrypt at cost 12 takes ~250 ms. The dataset intentionally reuses two
        # demo passwords, so hashing each distinct one once turns what would be
        # a several-minute load into a few hundred milliseconds.
        hashed: dict[str, str] = {}
        n = 0
        for r in rows(in_dir, "users"):
            pwd = r["password"]
            if pwd not in hashed:
                hashed[pwd] = hash_password(pwd)
            db.add(User(
                id=int(r["id"]), email=r["email"], full_name=r["full_name"],
                role=r["role"], hashed_password=hashed[pwd],
                tourist_id=int(r["tourist_id"]) if r["tourist_id"] else None,
                created_at=dt(r["created_at"]),
            ))
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["users"] = n
        print(f"  users={n} ({len(hashed)} distinct passwords hashed)")

        # ---------------- ID hash chains ----------------
        prev_hash: dict[int, str] = {}
        n = 0
        for r in rows(in_dir, "id_chain_events"):
            tid = int(r["tourist_id"])
            index = int(r["index"])
            previous = prev_hash.get(tid, hashchain.GENESIS_HASH)
            hashed_at = dt(r["timestamp"]).isoformat()
            block_hash, hashed_at = _chain_block(index, r["event"], r["data"],
                                                 previous, hashed_at)
            db.add(IdBlock(tourist_id=tid, index=index, event=r["event"], data=r["data"],
                           previous_hash=previous, hash=block_hash,
                           hashed_at=hashed_at, timestamp=dt(r["timestamp"])))
            prev_hash[tid] = block_hash
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["id_blocks"] = n
        print(f"  id_blocks={n}")

        # ---------------- location pings ----------------
        n = 0
        for r in rows(in_dir, "location_pings"):
            if limit_pings is not None and n >= limit_pings:
                break
            db.add(LocationPing(
                id=int(r["id"]), tourist_id=int(r["tourist_id"]), lat=float(r["lat"]),
                lng=float(r["lng"]), speed_kmh=float(r["speed_kmh"]),
                timestamp=dt(r["timestamp"]), anomaly_score=num(r["anomaly_score"]),
                is_anomaly=flag(r["is_anomaly"]),
            ))
            n += 1
            if n % BATCH == 0:
                db.commit()
                print(f"    ... {n:,} pings", flush=True)
        db.commit()
        counts["location_pings"] = n
        print(f"  location_pings={n:,}")

        # ---------------- incidents (before alerts: FK ordering) ----------------
        n = 0
        for r in rows(in_dir, "incidents"):
            db.add(Incident(
                id=int(r["id"]), tourist_id=int(r["tourist_id"]), type=r["type"],
                severity=r["severity"], status=r["status"], description=r["description"],
                lat=num(r["lat"]), lng=num(r["lng"]),
                assigned_unit_id=int(r["assigned_unit_id"]) if r["assigned_unit_id"] else None,
                detected_at=dt(r["detected_at"]), acknowledged_at=dt(r["acknowledged_at"]),
                dispatched_at=dt(r["dispatched_at"]), resolved_at=dt(r["resolved_at"]),
            ))
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["incidents"] = n

        n = 0
        for r in rows(in_dir, "incident_events"):
            db.add(IncidentEvent(id=int(r["id"]), incident_id=int(r["incident_id"]),
                                 status=r["status"], note=r["note"],
                                 timestamp=dt(r["timestamp"])))
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["incident_events"] = n
        print(f"  incidents={counts['incidents']}  incident_events={n}")

        # ---------------- alerts ----------------
        n = 0
        for r in rows(in_dir, "alerts"):
            db.add(Alert(
                id=int(r["id"]), tourist_id=int(r["tourist_id"]), type=r["type"],
                zone_id=int(r["zone_id"]) if r["zone_id"] else None,
                severity=r["severity"], message=r["message"], lat=num(r["lat"]),
                lng=num(r["lng"]), acknowledged=flag(r["acknowledged"]),
                created_at=dt(r["created_at"]),
            ))
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["alerts"] = n
        print(f"  alerts={n:,}")

        # ---------------- devices ----------------
        # The generator stores a deterministic key stub, not a usable credential.
        # A loaded band is registered but not drivable; re-register it through
        # POST /api/devices/register to get a real, one-time API key.
        n = 0
        device_key_hash = hash_password("synthetic-device-key")
        for r in rows(in_dir, "devices"):
            db.add(Device(
                id=int(r["id"]), device_id=r["device_id"], tourist_id=int(r["tourist_id"]),
                hashed_key=device_key_hash, firmware_version=r["firmware_version"],
                battery_pct=num(r["battery_pct"]), last_heartbeat=dt(r["last_heartbeat"]),
                active=flag(r["active"]), created_at=dt(r["created_at"]),
            ))
            n += 1
        db.commit()
        counts["devices"] = n

        # ---------------- E-FIRs ----------------
        n = 0
        for r in rows(in_dir, "efirs"):
            document_hash = hashchain._compute_hash(
                0, r["filed_at"], "EFIR", r["narrative"], hashchain.GENESIS_HASH)
            db.add(EFIR(
                id=int(r["id"]), fir_number=r["fir_number"],
                incident_id=int(r["incident_id"]), tourist_id=int(r["tourist_id"]),
                status=r["status"], narrative=r["narrative"],
                last_known_lat=num(r["last_known_lat"]),
                last_known_lng=num(r["last_known_lng"]),
                last_seen_at=dt(r["last_seen_at"]), document_hash=document_hash,
                filed_at=dt(r["filed_at"]), closed_at=dt(r["closed_at"]),
            ))
            n += 1
        db.commit()
        counts["efirs"] = n

        # ---------------- audit log ----------------
        n = 0
        for r in rows(in_dir, "audit_logs"):
            db.add(AuditLog(id=int(r["id"]), timestamp=dt(r["timestamp"]),
                            actor=r["actor"], action=r["action"], target=r["target"],
                            ip=r["ip"], detail=r["detail"], outcome=r["outcome"]))
            n += 1
            if n % BATCH == 0:
                db.commit()
        db.commit()
        counts["audit_logs"] = n
        print(f"  devices={counts['devices']}  efirs={counts['efirs']}  audit_logs={n:,}")

        # ---------------- verification ----------------
        sample = [t.id for t in db.query(Tourist.id).limit(25).all()]
        bad = [tid for tid in sample if not hashchain.verify_chain(db, tid)["valid"]]
        if bad:
            print(f"  WARNING: hash chain verification failed for tourists {bad}")
        else:
            print(f"  hash chains verified OK ({len(sample)} sampled)")
    finally:
        db.close()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_dir", default=DEFAULT_IN)
    ap.add_argument("--keep-existing", action="store_true",
                    help="append instead of replacing existing rows")
    ap.add_argument("--limit-pings", type=int, default=None,
                    help="load at most N location pings (the rest of the data is "
                         "small; this is the knob for a fast demo load)")
    args = ap.parse_args()

    manifest_path = os.path.join(args.in_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise SystemExit(
            f"No dataset at {args.in_dir}. Generate one first:\n"
            "  python -m app.scripts.generate_synthetic_dataset")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    print(f"Loading dataset from {args.in_dir} "
          f"(generated {manifest['parameters']['generated_at']}, "
          f"seed {manifest['parameters']['seed']})")

    counts = load(args.in_dir, args.keep_existing, args.limit_pings)

    print("\n=== Loaded ===")
    for table, count in counts.items():
        print(f"  {table:<20} {count:>10,}")
    print("\nAdmin login  : admin@tourism.gov.in / admin123")
    print("Tourist login: see users.csv (every tourist account uses 'tourist123')")


if __name__ == "__main__":
    main()
