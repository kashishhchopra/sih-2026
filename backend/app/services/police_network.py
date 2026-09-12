"""Area-Based Police Network: zone -> station routing, inter-station hand-off,
and the aggregated view that stands in for a "Central Safety Dashboard".

The model: the map is divided into safety `Zone`s (already used for risk
scoring); each zone is assigned to exactly one `PoliceStation`. An SOS/
incident opened inside a zone is auto-routed to that zone's station. Every
station can see the whole network's live incidents through
`central_dashboard`, and can hand a case to a peer station via
`forward_incident` -- e.g. because the tourist moved into another zone, or
the incident is actually closer to a neighbouring station.

    tourist location -> zone -> station  (assign_station)
                                   |
                          central dashboard (central_dashboard)
                                   |
                    station <-> station  (forward_incident)

Police Station Resource Fallback System
----------------------------------------
`assign_station` doesn't just hand every case to its zone's station
unconditionally -- it first checks that station's real-time capacity
(open-case load against `PoliceStation.max_concurrent_cases`). If the zone's
own station is at/over capacity, it automatically falls back to the next
best-suited station network-wide, ranked by distance, current workload, and
staffing (`rank_stations_for_point`) -- Station A -> Station B -> Station C
-- so an emergency is never delayed just because the nearest station is
overloaded. Every fallback hop is logged on the incident.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.emergency_location import EmergencyLocationPing
from app.models.incident import Incident, IncidentEvent
from app.models.incident_transfer import IncidentTransfer
from app.models.police import Camera, PoliceStation
from app.models.zone import Zone
from app.services import cctv, geo


def resolve_zone_for_point(db: Session, lat: float, lng: float) -> Zone | None:
    """Which zone (if any) a point falls inside. If more than one zone
    overlaps at that point, the highest-risk zone wins -- that is the one
    whose station should own the case."""
    zones = db.query(Zone).all()
    matches = geo.zones_containing_point(lat, lng, zones)
    if not matches:
        return None
    _RANK = {"restricted": 3, "high": 2, "medium": 1, "low": 0}
    return max(matches, key=lambda z: _RANK.get(z.risk_level, 0))


def station_for_zone(db: Session, zone_id: int) -> PoliceStation | None:
    return db.query(PoliceStation).filter(PoliceStation.zone_id == zone_id).first()


def station_for_point(db: Session, lat: float, lng: float) -> PoliceStation | None:
    """The station responsible for wherever (lat, lng) currently is."""
    zone = resolve_zone_for_point(db, lat, lng)
    if zone is None:
        return None
    return station_for_zone(db, zone.id)


def _station_workload(db: Session, station_id: int) -> int:
    """Open (non-resolved) cases currently assigned to a station -- the
    live half of its capacity check."""
    return (
        db.query(Incident)
        .filter(Incident.station_id == station_id, Incident.status != "resolved")
        .count()
    )


def station_capacity(db: Session, station: PoliceStation) -> dict:
    """A station's real-time resource status: how many cases it's carrying
    against how many it's staffed to run at once."""
    open_cases = _station_workload(db, station.id)
    max_cases = station.max_concurrent_cases
    return {
        "station_id": station.id,
        "open_cases": open_cases,
        "max_concurrent_cases": max_cases,
        "total_officers": station.total_officers,
        "has_capacity": open_cases < max_cases,
        "load_pct": round(100 * open_cases / max_cases, 1) if max_cases else 100.0,
    }


def rank_stations_for_point(db: Session, lat: float, lng: float) -> list[dict]:
    """Every station in the network, ranked for how well-suited each is to
    respond to (lat, lng) right now: stations with spare capacity first,
    then closest, then least loaded, then best-staffed -- the fallback
    order Station A -> Station B -> Station C follows this list."""
    ranked = []
    for s in db.query(PoliceStation).all():
        cap = station_capacity(db, s)
        ranked.append({
            "station": s,
            "distance_km": round(geo.haversine_m(lat, lng, s.lat, s.lng) / 1000, 2),
            **cap,
        })
    ranked.sort(key=lambda r: (not r["has_capacity"], r["distance_km"], r["load_pct"], -r["total_officers"]))
    return ranked


def assign_station(db: Session, incident: Incident) -> PoliceStation | None:
    """Route a freshly-opened incident to the station responsible for its
    zone, logging the hand-off. No-op (returns None) if the incident has no
    location or falls outside every zone -- it stays with the control room.

    Resource-aware: if that zone's own station is at/over capacity, walks
    the network-wide ranking (`rank_stations_for_point`) for the next
    best-suited station with room to take the case -- see this module's
    "Police Station Resource Fallback System" docstring. If literally every
    station in the network is at capacity, the case still goes to the
    nearest one rather than sit unassigned -- a busy network beats no
    response.
    """
    if incident.lat is None or incident.lng is None:
        return None
    zone = resolve_zone_for_point(db, incident.lat, incident.lng)
    if zone is None:
        return None
    primary = station_for_zone(db, zone.id)
    if primary is None:
        return None

    ranked = rank_stations_for_point(db, incident.lat, incident.lng)
    primary_entry = next((r for r in ranked if r["station"].id == primary.id), None)

    if primary_entry is not None and primary_entry["has_capacity"]:
        chosen = primary_entry
    else:
        with_capacity = [r for r in ranked if r["has_capacity"]]
        # Every station full: still dispatch -- to the nearest one -- rather
        # than leave the incident unassigned.
        chosen = with_capacity[0] if with_capacity else ranked[0]

    station = chosen["station"]
    incident.station_id = station.id

    if station.id == primary.id:
        note = f"Routed to {station.name} (area-based police network)"
    else:
        note = (
            f"{primary.name} at capacity ({primary_entry['open_cases']}/"
            f"{primary_entry['max_concurrent_cases']} cases) -- resource fallback "
            f"routed to {station.name} ({chosen['distance_km']} km, "
            f"{chosen['open_cases']}/{chosen['max_concurrent_cases']} cases, "
            f"{chosen['total_officers']} officers)"
        )
    db.add(IncidentEvent(incident_id=incident.id, status="station_assigned", note=note))
    return station


def forward_incident(
    db: Session, incident: Incident, to_station_id: int, note: str = "", actor: str = ""
) -> PoliceStation:
    """Hand an incident from its current station to another one in the
    network -- e.g. the tourist crossed into a neighbouring zone, or the
    receiving station is simply better placed to respond."""
    to_station = db.get(PoliceStation, to_station_id)
    if to_station is None:
        raise ValueError(f"No such station: {to_station_id}")

    from_station = db.get(PoliceStation, incident.station_id) if incident.station_id else None
    from_name = from_station.name if from_station else "control room"
    incident.station_id = to_station.id
    detail = f"Forwarded from {from_name} to {to_station.name}"
    if note:
        detail += f": {note}"
    if actor:
        detail += f" (by {actor})"
    db.add(IncidentEvent(incident_id=incident.id, status="forwarded", note=detail))
    return to_station


class TransferError(Exception):
    """Raised for a transfer request/response that fails a business rule --
    the API layer maps this to the right HTTP status."""


def _latest_location(db: Session, incident_id: int) -> EmergencyLocationPing | None:
    return (
        db.query(EmergencyLocationPing)
        .filter(EmergencyLocationPing.incident_id == incident_id)
        .order_by(EmergencyLocationPing.timestamp.desc())
        .first()
    )


def send_case(
    db: Session, incident: Incident, to_station_id: int, reason: str, actor: str,
    share_live_location: bool = True,
) -> IncidentTransfer:
    """One-click, no-approval hand-off: the case (and its live-location
    session, keyed by incident.id and never touched here) moves to
    `to_station_id` immediately -- the dashboard's "Send Case" action. Still
    writes a full IncidentTransfer row (status already "accepted", no
    "requested" interval) so the transfer/audit history stays complete; see
    request_transfer/accept_transfer below for the older two-step,
    receiving-station-approval alternative kept for API compatibility.
    """
    if incident.status == "resolved":
        raise TransferError("Cannot transfer a resolved case.")
    to_station = db.get(PoliceStation, to_station_id)
    if to_station is None:
        raise TransferError(f"No such station: {to_station_id}")
    if to_station_id == incident.station_id:
        raise TransferError("Case is already assigned to that station.")

    from_station_id = incident.station_id
    latest = _latest_location(db, incident.id)
    now = utc_now()
    transfer = IncidentTransfer(
        incident_id=incident.id,
        from_station_id=from_station_id,
        to_station_id=to_station_id,
        reason=reason,
        status="accepted",
        requested_by=actor,
        responded_by=actor,
        location_shared=share_live_location,
        latest_lat=latest.lat if latest else incident.lat,
        latest_lng=latest.lng if latest else incident.lng,
        latest_location_at=latest.timestamp if latest else None,
        requested_at=now,
        responded_at=now,
    )
    db.add(transfer)
    db.flush()

    forward_incident(
        db, incident, to_station_id,
        note=reason or "sent directly", actor=actor,
    )

    from app.websocket.manager import broadcast_sync
    broadcast_sync({
        "event": "transfer_accepted", "incident_id": incident.id, "transfer_id": transfer.id,
        "from_station_id": from_station_id, "to_station_id": to_station_id,
        "location_shared": share_live_location,
    })
    return transfer


def request_transfer(
    db: Session, incident: Incident, to_station_id: int, reason: str, actor: str,
    share_live_location: bool = True,
) -> IncidentTransfer:
    """Station A asks to hand a case to Station B. Does NOT move the case --
    the live-location session (keyed by incident.id, never by station) keeps
    flowing to Station A exactly as before until Station B accepts. See the
    module docstring's "Police Station Resource Fallback System" for the
    immediate, no-approval alternative (`forward_incident`) this workflow
    sits alongside rather than replaces.
    """
    if incident.status == "resolved":
        raise TransferError("Cannot transfer a resolved case.")
    to_station = db.get(PoliceStation, to_station_id)
    if to_station is None:
        raise TransferError(f"No such station: {to_station_id}")
    if to_station_id == incident.station_id:
        raise TransferError("Case is already assigned to that station.")

    existing = (
        db.query(IncidentTransfer)
        .filter(IncidentTransfer.incident_id == incident.id,
                IncidentTransfer.status == "requested")
        .first()
    )
    if existing is not None:
        raise TransferError(
            f"A transfer request (#{existing.id}) is already pending for this case."
        )

    latest = _latest_location(db, incident.id)
    transfer = IncidentTransfer(
        incident_id=incident.id,
        from_station_id=incident.station_id,
        to_station_id=to_station_id,
        reason=reason,
        status="requested",
        requested_by=actor,
        location_shared=share_live_location,
        latest_lat=latest.lat if latest else incident.lat,
        latest_lng=latest.lng if latest else incident.lng,
        latest_location_at=latest.timestamp if latest else None,
    )
    db.add(transfer)
    db.flush()

    from_station = db.get(PoliceStation, incident.station_id) if incident.station_id else None
    from_name = from_station.name if from_station else "control room"
    note = f"Transfer requested: {from_name} -> {to_station.name}"
    if reason:
        note += f" ({reason})"
    db.add(IncidentEvent(incident_id=incident.id, status="transfer_requested",
                         note=f"{note}, by {actor}" if actor else note))
    from app.websocket.manager import broadcast_sync
    broadcast_sync({
        "event": "transfer_requested", "incident_id": incident.id, "transfer_id": transfer.id,
        "from_station_id": incident.station_id, "to_station_id": to_station_id,
        "reason": reason,
    })
    return transfer


def _get_pending_transfer(db: Session, incident: Incident, transfer_id: int) -> IncidentTransfer:
    transfer = db.get(IncidentTransfer, transfer_id)
    if transfer is None or transfer.incident_id != incident.id:
        raise TransferError("Transfer request not found for this case.")
    if transfer.status != "requested":
        raise TransferError(f"Transfer #{transfer_id} is already {transfer.status}.")
    return transfer


def accept_transfer(
    db: Session, incident: Incident, transfer_id: int, actor: str
) -> IncidentTransfer:
    """Station B accepts: the case's current station changes, but the same
    live-location session (EmergencyLocationPing rows keyed by incident.id)
    just keeps recording against this incident -- nothing about the
    location feed itself is touched. Reuses `forward_incident` for the
    actual station hand-off + case-history entry, so there is exactly one
    code path that ever moves `Incident.station_id`.
    """
    transfer = _get_pending_transfer(db, incident, transfer_id)
    to_station = forward_incident(
        db, incident, transfer.to_station_id,
        note=f"transfer #{transfer.id} accepted" + (f": {transfer.reason}" if transfer.reason else ""),
        actor=actor,
    )
    transfer.status = "accepted"
    transfer.responded_by = actor
    transfer.responded_at = utc_now()

    from app.websocket.manager import broadcast_sync
    broadcast_sync({
        "event": "transfer_accepted", "incident_id": incident.id, "transfer_id": transfer.id,
        "from_station_id": transfer.from_station_id, "to_station_id": to_station.id,
    })
    return transfer


def reject_transfer(
    db: Session, incident: Incident, transfer_id: int, actor: str, reason: str = ""
) -> IncidentTransfer:
    """Station B declines: the case, and its live-location session, remain
    exactly where they were -- the original station stays responsible until
    some other station accepts a (new) transfer request."""
    transfer = _get_pending_transfer(db, incident, transfer_id)
    transfer.status = "rejected"
    transfer.responded_by = actor
    transfer.responded_at = utc_now()

    to_station = db.get(PoliceStation, transfer.to_station_id)
    note = f"Transfer #{transfer.id} rejected by {actor}"
    if reason:
        note += f": {reason}"
    db.add(IncidentEvent(incident_id=incident.id, status="transfer_rejected", note=note))

    from app.websocket.manager import broadcast_sync
    broadcast_sync({
        "event": "transfer_rejected", "incident_id": incident.id, "transfer_id": transfer.id,
        "to_station_id": to_station.id if to_station else transfer.to_station_id,
    })
    return transfer


def cancel_transfer(db: Session, incident: Incident, transfer_id: int, actor: str) -> IncidentTransfer:
    """The requesting station withdraws its own still-pending request."""
    transfer = _get_pending_transfer(db, incident, transfer_id)
    transfer.status = "cancelled"
    transfer.responded_by = actor
    transfer.responded_at = utc_now()
    db.add(IncidentEvent(incident_id=incident.id, status="transfer_cancelled",
                         note=f"Transfer #{transfer.id} cancelled by {actor}"))
    return transfer


def list_transfers(db: Session, incident_id: int) -> list[IncidentTransfer]:
    """Complete transfer history for a case, oldest first."""
    return (
        db.query(IncidentTransfer)
        .filter(IncidentTransfer.incident_id == incident_id)
        .order_by(IncidentTransfer.requested_at)
        .all()
    )


def list_pending_transfers(db: Session) -> list[IncidentTransfer]:
    """Every transfer request network-wide still awaiting accept/reject --
    the Central Safety Dashboard's "Incoming Transfer Requests" panel."""
    return (
        db.query(IncidentTransfer)
        .filter(IncidentTransfer.status == "requested")
        .order_by(IncidentTransfer.requested_at.desc())
        .all()
    )


def nearby_cameras(db: Session, lat: float, lng: float, radius_m: float = 1000) -> list[dict]:
    """Cameras within `radius_m` metres of a point, nearest first -- "nearby
    CCTV/camera information" for a responder looking at an incident."""
    cams = db.query(Camera).all()
    out = []
    for c in cams:
        dist = geo.haversine_m(lat, lng, c.lat, c.lng)
        if dist <= radius_m:
            out.append({
                "id": c.id, "label": c.label, "zone_id": c.zone_id,
                "lat": c.lat, "lng": c.lng, "status": c.status,
                "distance_m": round(dist, 1),
                # Stream metadata so a responder looking at nearby coverage
                # can tell which of those cameras actually has a feed. The
                # live connection state is NOT probed here -- that is
                # /cctv's job (services/cctv.py), which does it properly.
                "stream_url": cctv.strip_credentials(c.stream_url),
                "stream_type": c.stream_type or "none",
                "feed_source": c.feed_source or "manual",
                "assigned_station_id": cctv.resolve_station_id(db, c),
            })
    out.sort(key=lambda c: c["distance_m"])
    return out


def central_dashboard(db: Session) -> dict:
    """The interconnected network's shared view: every station, the zone it
    covers, and its current open-case load -- the "Central Safety Dashboard"
    every station in the network sees."""
    stations = db.query(PoliceStation).all()
    zones_by_id = {z.id: z for z in db.query(Zone).all()}
    open_incidents = (
        db.query(Incident).filter(Incident.status != "resolved").all()
    )
    by_station: dict[int, list[Incident]] = {}
    unassigned: list[Incident] = []
    for inc in open_incidents:
        if inc.station_id is not None:
            by_station.setdefault(inc.station_id, []).append(inc)
        else:
            unassigned.append(inc)

    stations_out = []
    for s in stations:
        zone = zones_by_id.get(s.zone_id) if s.zone_id else None
        cases = by_station.get(s.id, [])
        max_cases = s.max_concurrent_cases
        stations_out.append({
            "id": s.id, "name": s.name, "phone": s.phone,
            "contact_officer": s.contact_officer, "lat": s.lat, "lng": s.lng,
            "zone_id": s.zone_id, "zone_name": zone.name if zone else None,
            "open_incidents": len(cases),
            "critical_incidents": sum(1 for i in cases if i.severity == "critical"),
            "incident_ids": [i.id for i in cases],
            # Resource-fallback signals (see rank_stations_for_point): a
            # station at capacity is one an incoming case gets routed around.
            "total_officers": s.total_officers,
            "max_concurrent_cases": max_cases,
            "has_capacity": len(cases) < max_cases,
            "load_pct": round(100 * len(cases) / max_cases, 1) if max_cases else 100.0,
        })

    return {
        "generated_at": utc_now(),
        "stations": stations_out,
        "unassigned_incidents": [i.id for i in unassigned],
        "total_open_incidents": len(open_incidents),
    }
