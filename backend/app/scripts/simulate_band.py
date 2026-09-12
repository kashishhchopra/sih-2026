"""Live demo simulator for an IoT smart band.

Registers a virtual device against the first seeded tourist and drives the
telemetry endpoint (POST /devices/{id}/telemetry), including a scripted fall
event, so the dashboard's device roster and health_anomaly/fall_detected
alerts light up during a presentation without real hardware.

Run (backend must be running, seed must have been run first):
    python -m app.scripts.simulate_band
    python -m app.scripts.simulate_band --steps 30 --interval 2
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from contextlib import suppress

import httpx

with suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000/api"
random.seed(11)


def _admin_token() -> str:
    r = httpx.post(f"{BASE}/auth/login",
                   data={"username": "admin@tourism.gov.in", "password": "admin123"})
    r.raise_for_status()
    return r.json()["access_token"]


def _first_tourist(token: str) -> dict:
    r = httpx.get(f"{BASE}/tourists", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    tourists = r.json()
    if not tourists:
        raise SystemExit("No tourists found. Run:  python -m app.scripts.seed")
    return tourists[0]


def _register_device(token: str, tourist_id: int, device_id: str) -> str:
    r = httpx.post(f"{BASE}/devices/register",
                   json={"tourist_id": tourist_id, "device_id": device_id,
                        "firmware_version": "2.1.0-demo"},
                   headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 400:
        print(f"Device {device_id} already registered; re-registering with a fresh id.")
        device_id = f"{device_id}-{random.randint(1000, 9999)}"
        return _register_device(token, tourist_id, device_id)
    r.raise_for_status()
    return r.json()["api_key"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args()

    token = _admin_token()
    tourist = _first_tourist(token)
    device_id = "BAND-DEMO-001"
    api_key = _register_device(token, tourist["id"], device_id)
    print(f"Registered {device_id} for {tourist['full_name']}\n")

    lat = tourist.get("last_lat") or 26.1445
    lng = tourist.get("last_lng") or 91.7362
    battery = 92.0
    headers = {"X-Device-Key": api_key}

    for step in range(1, args.steps + 1):
        lat += random.uniform(-0.0015, 0.0015)
        lng += random.uniform(-0.0015, 0.0015)
        battery = max(5.0, battery - random.uniform(0.1, 0.4))
        heart_rate = random.uniform(65, 95)
        fall = step == 12  # scripted fall event mid-run
        if fall:
            heart_rate = 145  # a fall spikes heart rate too

        body = {
            "lat": lat, "lng": lng, "speed_kmh": random.uniform(2, 8),
            "heart_rate_bpm": heart_rate, "battery_pct": round(battery, 1),
            "sos_pressed": False, "fall_detected": fall,
        }
        r = httpx.post(f"{BASE}/devices/{device_id}/telemetry", json=body,
                       headers=headers, timeout=10)
        r.raise_for_status()
        out = r.json()
        tag = f"  ⚠ {out['alerts_raised']}" if out.get("alerts_raised") else ""
        if fall:
            tag += "  [SCRIPTED FALL EVENT]"
        print(f"[step {step:02d}] battery={battery:5.1f}%  hr={heart_rate:5.1f}bpm  "
              f"score={out['safety_score']:>5}{tag}")
        time.sleep(args.interval)

    print("\nBand simulation finished.")


if __name__ == "__main__":
    main()
