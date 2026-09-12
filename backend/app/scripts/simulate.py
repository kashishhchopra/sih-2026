"""Live demo simulator: moves seeded tourists around the map and injects anomalies.

Drives the real API (POST /tourists/{id}/location, SOS) so the dashboard and
WebSocket feed light up during a presentation.

Run (backend must be running):
    python -m app.scripts.simulate                # normal wandering + scripted anomalies
    python -m app.scripts.simulate --steps 200 --interval 1.5

Scripted events (by step):
    step 8  : Tourist 3 -> route deviation + high-speed anomaly (abduction pattern)
    step 14 : Tourist 2 -> walks into Old Market high-risk geofence
    step 20 : Tourist 4 -> prolonged inactivity anomaly
    step 26 : Tourist 5 -> presses SOS
"""
from __future__ import annotations

import argparse
import contextlib
import random
import sys
import time

import httpx

# Windows consoles default to cp1252 and choke on emoji/symbols in output.
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000/api"
random.seed(7)


def get_tourists() -> list[dict]:
    # public-ish: we log in as admin to list tourists
    r = httpx.post(f"{BASE}/auth/login",
                   data={"username": "admin@tourism.gov.in", "password": "admin123"})
    r.raise_for_status()
    token = r.json()["access_token"]
    tr = httpx.get(f"{BASE}/tourists", headers={"Authorization": f"Bearer {token}"})
    tr.raise_for_status()
    return tr.json(), token


def send_location(tid: int, lat: float, lng: float, speed: float, token: str) -> dict:
    r = httpx.post(f"{BASE}/tourists/{tid}/location",
                   json={"lat": lat, "lng": lng, "speed_kmh": speed},
                   headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()


def send_sos(tid: int, lat: float, lng: float, token: str) -> dict:
    r = httpx.post(f"{BASE}/tourists/{tid}/sos",
                   json={"lat": lat, "lng": lng, "message": "Help! Being followed."},
                   headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()


def acknowledge_incident(incident_id: int, token: str) -> dict:
    r = httpx.post(f"{BASE}/incidents/{incident_id}/acknowledge",
                   headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()


def get_risk_forecast(tid: int, token: str) -> dict:
    r = httpx.get(f"{BASE}/tourists/{tid}/risk-forecast",
                  headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--forecast", action="store_true",
                    help="After each step, print the scripted tourist's +15/+30/+60 min risk forecast")
    ap.add_argument("--no-ack", action="store_true",
                    help="Do not acknowledge the scripted SOS (step 26) -- lets the escalation "
                         "clock visibly advance stages instead of stopping at first dispatch")
    args = ap.parse_args()

    tourists, token = get_tourists()
    if not tourists:
        print("No tourists found. Run:  python -m app.scripts.seed")
        return

    # working position per tourist
    pos = {t["id"]: [t["last_lat"] or 26.1445, t["last_lng"] or 91.7362] for t in tourists}
    ids = [t["id"] for t in tourists]
    print(f"Simulating {len(ids)} tourists for {args.steps} steps...\n")

    for step in range(1, args.steps + 1):
        for t in tourists:
            tid = t["id"]
            lat, lng = pos[tid]
            speed = random.uniform(2, 12)

            # ---- scripted anomalies ----
            if step == 8 and t is tourists[2 % len(tourists)]:
                lat += 0.03
                lng += 0.03
                speed = 165  # jump + high speed
                print(f"[step {step}] ANOMALY: {t['full_name']} high-speed jump (abduction pattern)")
            elif step == 14 and t is tourists[1 % len(tourists)]:
                lat, lng = 26.1650, 91.7500  # Old Market high-risk zone
                print(f"[step {step}] GEOFENCE: {t['full_name']} entering Old Market high-risk zone")
            elif step == 20 and t is tourists[3 % len(tourists)]:
                speed = 0.1  # inactivity (dt grows between polls)
                print(f"[step {step}] ANOMALY: {t['full_name']} prolonged inactivity")
            elif step == 26 and t is tourists[4 % len(tourists)]:
                res = send_sos(tid, lat, lng, token)
                unit = res.get("nearest_unit", {})
                print(f"[step {step}] SOS: {t['full_name']} -> dispatched "
                      f"{unit.get('name') if unit else 'n/a'} ({unit.get('distance_km') if unit else '?'} km)")
                if args.no_ack:
                    print(f"[step {step}] --no-ack set: leaving the incident unacknowledged "
                          f"so escalation stages advance on their own")
                else:
                    with contextlib.suppress(Exception):
                        acknowledge_incident(res["incident_id"], token)
                        print(f"[step {step}] incident #{res['incident_id']} acknowledged")
                continue
            else:
                # normal wander
                lat += random.uniform(-0.002, 0.002)
                lng += random.uniform(-0.002, 0.002)

            pos[tid] = [lat, lng]
            try:
                out = send_location(tid, lat, lng, speed, token)
                flags = out.get("alerts_raised") or []
                tag = f"  ⚠ {flags}" if flags else ""
                print(f"[step {step}] {t['full_name']:<14} score={out['safety_score']:>5} "
                      f"band={out['band']:<8}{tag}")
            except Exception as e:  # noqa: BLE001
                print(f"[step {step}] {t['full_name']} update failed: {e}")

        if args.forecast:
            scripted = tourists[1 % len(tourists)]
            try:
                fc = get_risk_forecast(scripted["id"], token)["forecast"]
                summary = ", ".join(f"+{f['minutes']}m={f['score']} ({f['band']})" for f in fc)
                print(f"[step {step}] FORECAST {scripted['full_name']:<14} {summary}")
            except Exception as e:  # noqa: BLE001
                print(f"[step {step}] forecast fetch failed: {e}")

        time.sleep(args.interval)

    print("\nSimulation finished.")


if __name__ == "__main__":
    main()
