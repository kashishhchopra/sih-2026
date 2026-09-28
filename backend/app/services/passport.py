"""Digital Safety Passport: a curated view of data the tamper-evident ID
chain already anchors, plus current live state -- the minimum a responder
needs in an emergency, in one scan.
"""
from __future__ import annotations

import base64
import io
import json

import qrcode
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.tourist import Tourist
from app.services import consular


def _qr_base64(tourist: Tourist) -> str:
    content = json.dumps({
        "digital_id": tourist.digital_id,
        "name": tourist.full_name,
        "valid_until": tourist.trip_end.isoformat(),
    })
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def build_passport(db: Session, tourist: Tourist) -> dict:
    device = (
        db.query(Device)
        .filter(Device.tourist_id == tourist.id, Device.active.is_(True))
        .order_by(Device.last_heartbeat.desc())
        .first()
    )
    country_code = consular.normalize_nationality(
        tourist.nationality_code or tourist.nationality
    )
    primary_mission = None
    if country_code and country_code != "IN":
        missions = consular.missions_for(country_code)
        primary_mission = missions[0] if missions else None

    return {
        "digital_id": tourist.digital_id,
        "full_name": tourist.full_name,
        "nationality": tourist.nationality,
        "nationality_code": country_code,
        # A responder scanning a foreign tourist's QR sees the consulate
        # phone number in the same glance as everything else -- no separate
        # lookup needed in whatever moment this passport actually gets used.
        "consular_phone": (primary_mission or {}).get("phone"),
        "preferred_language": tourist.preferred_language,
        "phone": tourist.phone,
        "emergency_contacts": json.loads(tourist.emergency_contacts or "[]"),
        "itinerary": json.loads(tourist.itinerary or "[]"),
        "trip_start": tourist.trip_start,
        "trip_end": tourist.trip_end,
        "is_valid": tourist.is_valid,
        "current_status": tourist.status,
        "safety_score": tourist.safety_score,
        "last_lat": tourist.last_lat,
        "last_lng": tourist.last_lng,
        "last_seen": tourist.last_seen,
        "device": {
            "device_id": device.device_id,
            "battery_pct": device.battery_pct,
            "is_online": device.is_online,
        } if device else None,
        "qr_png_base64": _qr_base64(tourist),
    }
