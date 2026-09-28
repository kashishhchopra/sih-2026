"""Area-Based Police Network: station directory, the Central Safety Dashboard,
inter-station case hand-off, and nearby-camera lookup.

See services/police_network.py for the routing/forwarding logic this thinly
wraps.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_admin_or_responder
from app.db.session import get_db
from app.models.disaster import DisasterAdvisory
from app.models.incident import Incident
from app.models.police import Camera, PoliceStation
from app.models.user import User
from app.schemas.disaster import DisasterAdvisoryOut, DisasterAdvisoryWithImpact
from app.schemas.incident import IncidentOut
from app.schemas.police_network import (
    CameraCreate,
    CameraOut,
    CentralDashboardOut,
    ForwardIncidentRequest,
    PoliceStationCreate,
    PoliceStationOut,
    SendCaseIn,
    StationCapacityOut,
    StationFallbackOut,
    TransferOut,
    TransferRequestIn,
    TransferRespondIn,
)
from app.services import audit, disaster, police_network

router = APIRouter(prefix="/police-network", tags=["police-network"])


# ---------------- station directory ----------------
@router.get("/stations", response_model=list[PoliceStationOut])
def list_stations(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(PoliceStation).all()


@router.post("/stations", response_model=PoliceStationOut, status_code=201)
def create_station(payload: PoliceStationCreate, db: Session = Depends(get_db),
                   _: User = Depends(require_admin)):
    if payload.zone_id is not None:
        existing = police_network.station_for_zone(db, payload.zone_id)
        if existing is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Zone {payload.zone_id} is already covered by station {existing.id}",
            )
    station = PoliceStation(**payload.model_dump())
    db.add(station)
    db.commit()
    db.refresh(station)
    return station


# ---------------- Central Safety Dashboard ----------------
@router.get("/dashboard", response_model=CentralDashboardOut)
def central_dashboard(db: Session = Depends(get_db),
                      _: User = Depends(require_admin_or_responder)):
    """The shared, interconnected view every station in the network sees:
    each station's zone, its current open cases, and anything not yet
    attributed to any station."""
    return police_network.central_dashboard(db)


# ---------------- zone -> station lookup ----------------
@router.get("/zones/{zone_id}/station", response_model=PoliceStationOut)
def station_for_zone(zone_id: int, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    station = police_network.station_for_zone(db, zone_id)
    if station is None:
        raise HTTPException(status_code=404, detail="No station covers this zone")
    return station


@router.get("/locate", response_model=PoliceStationOut)
def locate_station(lat: float = Query(...), lng: float = Query(...),
                   db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Which station is responsible for an arbitrary point right now --
    e.g. a tourist's live location, before any incident exists."""
    station = police_network.station_for_point(db, lat, lng)
    if station is None:
        raise HTTPException(status_code=404, detail="No station covers this location")
    return station


# ---------------- station-scoped active cases (police dashboard) ----------------
@router.get("/stations/{station_id}/incidents", response_model=list[IncidentOut])
def station_incidents(station_id: int, include_resolved: bool = False,
                      db: Session = Depends(get_db),
                      _: User = Depends(require_admin_or_responder)):
    """Active emergency cases currently assigned to one station -- the police
    dashboard's own worklist. `Incident.station_id` is always the *current*
    authorized handler (moved by forward/accept-transfer, never duplicated),
    so this is a plain filter, not a join through any transfer history."""
    station = db.get(PoliceStation, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    q = db.query(Incident).filter(Incident.station_id == station_id)
    if not include_resolved:
        q = q.filter(Incident.status != "resolved")
    from app.api.incidents import _hydrate_tourist_info

    return _hydrate_tourist_info(db, q.order_by(Incident.detected_at.desc()).all())


# ---------------- resource fallback ----------------
@router.get("/stations/{station_id}/capacity", response_model=StationCapacityOut)
def station_capacity(station_id: int, db: Session = Depends(get_db),
                     _: User = Depends(require_admin_or_responder)):
    """One station's live resource status -- open cases against the number
    it's staffed to run at once. See services/police_network.py."""
    station = db.get(PoliceStation, station_id)
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return {"name": station.name, **police_network.station_capacity(db, station)}


@router.get("/fallback-preview", response_model=list[StationFallbackOut])
def fallback_preview(lat: float = Query(...), lng: float = Query(...),
                     db: Session = Depends(get_db),
                     _: User = Depends(require_admin_or_responder)):
    """The Police Station Resource Fallback order for a location: every
    station ranked by spare capacity, distance, workload and staffing --
    i.e. exactly who would take an emergency here, and who it would fall
    back to (Station A -> Station B -> Station C) if the first is
    overloaded. See services/police_network.py:rank_stations_for_point."""
    ranked = police_network.rank_stations_for_point(db, lat, lng)
    return [
        {
            "station_id": r["station_id"], "name": r["station"].name,
            "distance_km": r["distance_km"], "open_cases": r["open_cases"],
            "max_concurrent_cases": r["max_concurrent_cases"],
            "total_officers": r["total_officers"], "has_capacity": r["has_capacity"],
            "load_pct": r["load_pct"],
        }
        for r in ranked
    ]


# ---------------- disaster & weather monitoring ----------------
@router.get("/disaster-summary", response_model=list[DisasterAdvisoryWithImpact])
def disaster_summary(db: Session = Depends(get_db),
                     _: User = Depends(require_admin_or_responder)):
    """Active hazard advisories enriched for the Police Network Dashboard's
    Disaster & Weather Monitoring section: which zone, how many tourists are
    currently inside it, and the police station responsible for that zone --
    the same DisasterAdvisory data every tourist dashboard reads (see
    services/disaster.py), joined onto this app's existing station/zone
    architecture rather than a separate police-only alert list."""
    advisories = (
        db.query(DisasterAdvisory)
        .filter(DisasterAdvisory.active.is_(True))
        .order_by(DisasterAdvisory.issued_at.desc())
        .all()
    )
    out = []
    for a in advisories:
        station = police_network.station_for_zone(db, a.zone_id)
        out.append(DisasterAdvisoryWithImpact(
            **DisasterAdvisoryOut.model_validate(a).model_dump(),
            affected_tourists=disaster.affected_tourist_count(db, a),
            station_id=station.id if station else None,
            station_name=station.name if station else None,
        ))
    return out


# ---------------- inter-station hand-off ----------------
@router.post("/incidents/{incident_id}/forward", response_model=IncidentOut)
def forward_incident(incident_id: int, payload: ForwardIncidentRequest, request: Request,
                     db: Session = Depends(get_db),
                     user: User = Depends(require_admin_or_responder)):
    """Forward a case from its current station to another one in the
    network, e.g. because the tourist moved into a neighbouring zone."""
    from app.api.incidents import _get_incident_or_404

    inc = _get_incident_or_404(incident_id, db)
    try:
        police_network.forward_incident(
            db, inc, payload.to_station_id, note=payload.note, actor=user.email
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    audit.record(db, "forward_incident", actor=user.email, target=str(incident_id),
                detail=f"to_station={payload.to_station_id}", request=request)
    db.commit()
    db.refresh(inc)
    return inc


# ---------------- case transfer: direct send (dashboard's "Send Case") ----------------
# One click, no receiving-station approval step -- the case (and its
# live-location session, keyed by incident_id and never touched here) moves
# immediately. This is what the Central Safety Dashboard's transfer panel
# uses; see services/police_network.py:send_case.
@router.post("/incidents/{incident_id}/transfer/send", response_model=TransferOut, status_code=201)
def send_case(incident_id: int, payload: SendCaseIn, request: Request,
             db: Session = Depends(get_db),
             user: User = Depends(require_admin_or_responder)):
    from app.api.incidents import _get_incident_or_404

    inc = _get_incident_or_404(incident_id, db)
    try:
        transfer = police_network.send_case(
            db, inc, payload.to_station_id, payload.reason, actor=user.email,
            share_live_location=payload.share_live_location,
        )
    except police_network.TransferError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit.record(db, "send_case", actor=user.email, target=str(incident_id),
                detail=f"to_station={payload.to_station_id}", request=request)
    db.commit()
    db.refresh(transfer)
    return transfer


# ---------------- case transfer: request / accept / reject / cancel ----------------
# The consent-based counterpart to `send_case`/`forward_incident` above: a
# case moves to another station only once that station accepts, and the
# live-location session (services/emergency_location.py, keyed by
# incident_id) is never re-created or interrupted by any of this -- see
# services/police_network.py module docstring and app/models/incident_transfer.py.
@router.post("/incidents/{incident_id}/transfer", response_model=TransferOut, status_code=201)
def request_transfer(incident_id: int, payload: TransferRequestIn, request: Request,
                     db: Session = Depends(get_db),
                     user: User = Depends(require_admin_or_responder)):
    from app.api.incidents import _get_incident_or_404

    inc = _get_incident_or_404(incident_id, db)
    try:
        transfer = police_network.request_transfer(
            db, inc, payload.to_station_id, payload.reason, actor=user.email
        )
    except police_network.TransferError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit.record(db, "request_transfer", actor=user.email, target=str(incident_id),
                detail=f"to_station={payload.to_station_id}", request=request)
    db.commit()
    db.refresh(transfer)
    return transfer


@router.post("/incidents/{incident_id}/transfer/{transfer_id}/accept", response_model=IncidentOut)
def accept_transfer(incident_id: int, transfer_id: int, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_admin_or_responder)):
    from app.api.incidents import _get_incident_or_404

    inc = _get_incident_or_404(incident_id, db)
    try:
        police_network.accept_transfer(db, inc, transfer_id, actor=user.email)
    except police_network.TransferError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit.record(db, "accept_transfer", actor=user.email, target=str(incident_id),
                detail=f"transfer={transfer_id}", request=request)
    db.commit()
    db.refresh(inc)
    return inc


@router.post("/incidents/{incident_id}/transfer/{transfer_id}/reject", response_model=TransferOut)
def reject_transfer(incident_id: int, transfer_id: int, payload: TransferRespondIn, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(require_admin_or_responder)):
    from app.api.incidents import _get_incident_or_404

    inc = _get_incident_or_404(incident_id, db)
    try:
        transfer = police_network.reject_transfer(db, inc, transfer_id, actor=user.email,
                                                   reason=payload.reason)
    except police_network.TransferError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    audit.record(db, "reject_transfer", actor=user.email, target=str(incident_id),
                detail=f"transfer={transfer_id}", request=request)
    db.commit()
    db.refresh(transfer)
    return transfer


@router.post("/incidents/{incident_id}/transfer/{transfer_id}/cancel", response_model=TransferOut)
def cancel_transfer(incident_id: int, transfer_id: int, db: Session = Depends(get_db),
                    user: User = Depends(require_admin_or_responder)):
    from app.api.incidents import _get_incident_or_404

    inc = _get_incident_or_404(incident_id, db)
    try:
        transfer = police_network.cancel_transfer(db, inc, transfer_id, actor=user.email)
    except police_network.TransferError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    db.refresh(transfer)
    return transfer


@router.get("/incidents/{incident_id}/transfers", response_model=list[TransferOut])
def list_transfers(incident_id: int, db: Session = Depends(get_db),
                   _: User = Depends(require_admin_or_responder)):
    """Complete transfer history for a case -- every request, whoever raised
    it, and how it was resolved, oldest first."""
    from app.api.incidents import _get_incident_or_404

    _get_incident_or_404(incident_id, db)
    return police_network.list_transfers(db, incident_id)


@router.get("/transfers/pending", response_model=list[TransferOut])
def pending_transfers(db: Session = Depends(get_db),
                      _: User = Depends(require_admin_or_responder)):
    """Every transfer request network-wide still awaiting accept/reject."""
    return police_network.list_pending_transfers(db)


# ---------------- CCTV / camera directory ----------------
@router.get("/cameras/nearby", response_model=list[CameraOut])
def cameras_nearby(lat: float = Query(...), lng: float = Query(...),
                   radius_m: float = Query(1000, gt=0, le=20000),
                   db: Session = Depends(get_db),
                   _: User = Depends(require_admin_or_responder)):
    return police_network.nearby_cameras(db, lat, lng, radius_m)


@router.post("/cameras", response_model=CameraOut, status_code=201)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db),
                  _: User = Depends(require_admin)):
    cam = Camera(**payload.model_dump())
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam
