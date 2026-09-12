"""SOS live-location sharing: turns an active emergency incident into a
real-time position feed the police network can watch move.

Real GPS, real transport (this app's existing WebSocket push -- see
app/websocket/manager.py, already used for the admin alert feed and each
tourist's own channel; no new transport technology needed). The one thing
that is ever simulated is the position itself, and only when the frontend
explicitly marks a ping `demo: true` (its own random-walk fallback for a
device/browser with no real GPS, matching this project's existing
SIMULATE_GPS convention for ordinary tracking) -- that flag is stored and
surfaced to police, never silently dropped.

Anti-spoofing here is intentionally light-touch, matching the rest of this
project's safety-scoring philosophy: an implausible implied speed between
two consecutive pings is FLAGGED (`anomaly_flag`), never used to auto-raise
or auto-resolve anything. A human decides what an anomalous reading means;
this module only ever reports what the numbers say.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models.emergency_location import EmergencyLocationPing
from app.models.incident import Incident, IncidentEvent
from app.models.incident_transfer import IncidentTransfer
from app.models.police import PoliceStation
from app.models.tourist import Tourist
from app.services.geo import haversine_m
from app.websocket.manager import broadcast_sync, notify_tourist_sync

# Only these incident lifecycle stages are ever eligible for live tracking --
# a resolved case has nothing left to track, matching update_incident's own
# lifecycle rules (app/api/incidents.py) rather than inventing a second one.
_TRACKABLE_STATUSES = ("detected", "acknowledged", "dispatched")


class EmergencyLocationError(Exception):
    """Raised for a request that fails validation/authorization at the
    service layer -- the API layer maps this to the right HTTP status."""


def start_tracking(db: Session, incident: Incident) -> None:
    """Turn live tracking on for a freshly-opened SOS incident. Idempotent."""
    incident.live_tracking_active = True


def stop_tracking(db: Session, incident: Incident, reason: str) -> None:
    """Turn live tracking off without touching the incident's own status --
    stopping *sharing* is the tourist's call; closing the *case* stays the
    responder's (see update_incident's RBAC in app/api/incidents.py)."""
    if not incident.live_tracking_active:
        return
    incident.live_tracking_active = False
    db.add(IncidentEvent(incident_id=incident.id, status=incident.status,
                         note=f"Live location sharing stopped: {reason}"))
    notify_tourist_sync(incident.tourist_id, {
        "event": "emergency_tracking_stopped", "incident_id": incident.id, "reason": reason,
    })
    broadcast_sync({
        "event": "emergency_tracking_stopped", "incident_id": incident.id,
        "tourist_id": incident.tourist_id,
    })


def _implied_speed_kmh(a: EmergencyLocationPing, lat: float, lng: float, now: datetime) -> float:
    # Floored at 1 second, same as services/monitoring.py's regular ping
    # pipeline -- two pings can genuinely arrive within the same second (a
    # fast GPS update rate, or two requests racing slightly), and dividing a
    # real short distance by a near-zero time would read as an impossible
    # speed for perfectly normal movement.
    dt_s = max((now - a.timestamp).total_seconds(), 1.0)
    dist_km = haversine_m(a.lat, a.lng, lat, lng) / 1000
    return dist_km / (dt_s / 3600)


def record_location(
    db: Session, incident: Incident, lat: float, lng: float,
    accuracy_m: float | None, speed_kmh: float | None, heading_deg: float | None,
    demo: bool = False,
) -> EmergencyLocationPing:
    """Record one live-location ping for an active emergency. Raises
    EmergencyLocationError if the incident isn't currently trackable --
    the API layer is responsible for authorization (whose incident this is)
    before ever calling this."""
    if incident.status not in _TRACKABLE_STATUSES:
        raise EmergencyLocationError("This emergency is no longer active.")
    if not incident.live_tracking_active:
        raise EmergencyLocationError("Live location sharing is not active for this emergency.")

    now = utc_now()
    last = (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == incident.id)
        .order_by(EmergencyLocationPing.timestamp.desc())
        .first()
    )
    anomaly = False
    if last is not None:
        implied = _implied_speed_kmh(last, lat, lng, now)
        if implied > settings.EMERGENCY_LOCATION_MAX_PLAUSIBLE_KMH:
            anomaly = True

    ping = EmergencyLocationPing(
        incident_id=incident.id, lat=lat, lng=lng, accuracy_m=accuracy_m,
        speed_kmh=speed_kmh, heading_deg=heading_deg, timestamp=now,
        anomaly_flag=anomaly, demo=demo,
    )
    db.add(ping)
    incident.lat, incident.lng = lat, lng
    db.flush()

    # Bounded trail: never an unbounded location history, only "recent path
    # during an active emergency" -- see EMERGENCY_LOCATION_TRAIL_MAX_POINTS.
    keep_ids = {
        row[0] for row in (
            db.query(EmergencyLocationPing.id)
            .filter(EmergencyLocationPing.incident_id == incident.id)
            .order_by(EmergencyLocationPing.timestamp.desc())
            .limit(settings.EMERGENCY_LOCATION_TRAIL_MAX_POINTS)
            .all()
        )
    }
    (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == incident.id)
        .filter(~EmergencyLocationPing.id.in_(keep_ids))
        .delete(synchronize_session=False)
    )

    payload = {
        "event": "emergency_location", "incident_id": incident.id,
        "tourist_id": incident.tourist_id, "lat": lat, "lng": lng,
        "accuracy_m": accuracy_m, "speed_kmh": speed_kmh, "heading_deg": heading_deg,
        "timestamp": now.isoformat(), "anomaly_flag": anomaly, "demo": demo,
    }
    broadcast_sync(payload)  # police/control-room feed (admin-only WS)
    notify_tourist_sync(incident.tourist_id, {**payload, "event": "emergency_location_ack"})
    return ping


def location_status(last_ping_at: datetime | None) -> tuple[str, float | None]:
    """LIVE / STALE / OFFLINE / NO_DATA -- purely a function of recency, so
    the dashboard never claims "LIVE" once updates have actually stopped."""
    if last_ping_at is None:
        return "no_data", None
    age_s = (utc_now() - last_ping_at).total_seconds()
    if age_s <= settings.EMERGENCY_LOCATION_LIVE_SECONDS:
        return "live", age_s
    if age_s <= settings.EMERGENCY_LOCATION_STALE_SECONDS:
        return "stale", age_s
    return "offline", age_s


def build_track(db: Session, incident: Incident) -> dict:
    """Everything the police live map needs for one incident, in one call --
    see schemas.emergency_location.EmergencyTrackOut."""
    tourist = db.get(Tourist, incident.tourist_id)
    station = db.get(PoliceStation, incident.station_id) if incident.station_id else None
    trail = (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == incident.id)
        .order_by(EmergencyLocationPing.timestamp.desc())
        .limit(settings.EMERGENCY_LOCATION_TRAIL_MAX_POINTS)
        .all()
    )
    latest = trail[0] if trail else None
    status, age_s = location_status(latest.timestamp if latest else None)
    # Whether a hand-off to another station is awaiting that station's
    # accept/reject -- the live-location feed above is completely unaffected
    # either way (see app/models/incident_transfer.py): this is purely a
    # dashboard signal that the case's *station* may be about to change.
    pending_transfer = (
        db.query(IncidentTransfer)
        .filter(IncidentTransfer.incident_id == incident.id, IncidentTransfer.status == "requested")
        .order_by(IncidentTransfer.requested_at.desc())
        .first()
    )
    return {
        "incident_id": incident.id,
        "tourist_id": incident.tourist_id,
        "tourist_name": tourist.full_name if tourist else "Unknown",
        "digital_id": tourist.digital_id if tourist else "",
        # Full case + tourist detail, so a station receiving a transferred
        # case has everything it needs in this one call -- it never has to
        # separately request the tourist's identity/contact information
        # from whoever sent the case (see the "Send Case" panel's
        # docstring in police_network.py:send_case).
        "tourist_phone": tourist.phone if tourist else None,
        "tourist_nationality": tourist.nationality if tourist else None,
        "tourist_photo": tourist.photo if tourist else None,
        "safety_score": tourist.safety_score if tourist else None,
        "hotel": tourist.hotel if tourist else None,
        "emergency_contacts": json.loads(tourist.emergency_contacts) if tourist and tourist.emergency_contacts else [],
        "incident_type": incident.type,
        "severity": incident.severity,
        "status": incident.status,
        "description": incident.description,
        "detected_at": incident.detected_at,
        "live_tracking_active": incident.live_tracking_active,
        "station_id": station.id if station else None,
        "station_name": station.name if station else None,
        "location_status": status,
        "seconds_since_update": age_s,
        "latest": latest,
        "trail": list(reversed(trail)),  # oldest -> newest, for drawing a path
        "pending_transfer_id": pending_transfer.id if pending_transfer else None,
        "pending_transfer_to_station_id": pending_transfer.to_station_id if pending_transfer else None,
    }


def list_active_emergencies(db: Session) -> list[dict]:
    """Every incident currently sharing live location -- the "LIVE
    EMERGENCIES" section of the central safety dashboard."""
    incidents = (
        db.query(Incident)
        .filter(Incident.live_tracking_active.is_(True))
        .filter(Incident.status.in_(_TRACKABLE_STATUSES))
        .order_by(Incident.detected_at.desc())
        .all()
    )
    return [build_track(db, inc) for inc in incidents]
