import base64
import hashlib
import io
import json
import uuid

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    require_admin,
    require_self_admin_or_responder,
    require_self_or_admin,
)
from app.core.config import settings
from app.core.pagination import PageParams
from app.core.ratelimit import registration_rate_limit
from app.core.security import hash_password
from app.core.time import utc_now
from app.db.session import get_db
from app.models.checkin import CheckIn
from app.models.tourist import IdBlock, LocationPing, Tourist
from app.models.user import User
from app.models.zone import Zone
from app.schemas.checkin import CheckInCreate, CheckInOut
from app.schemas.liveness import LivenessVerifyRequest, LivenessVerifyResponse
from app.schemas.tourist import (
    DuressPinSet,
    IdBlockOut,
    LocationUpdate,
    PrivacySettingsUpdate,
    SafetyScoreOut,
    TouristCreate,
    TouristOut,
)
from app.services import audit, consular, hashchain, liveness, privacy
from app.services import passport as passport_service
from app.services import tourist_id as tourist_id_service
from app.services.forecast import DEFAULT_HORIZONS_MIN, forecast_risk
from app.services.monitoring import process_ping
from app.services.navigation import get_navigation_guidance
from app.services.nearby import find_nearby
from app.services.routing import recommend_route
from app.services.safety import compute_safety_score
from app.services.safety_card import build_safety_card
from app.services.trajectory import predict_trajectory, predicts_crosses_zone

router = APIRouter(prefix="/tourists", tags=["tourists"])


def _generate_digital_id(name: str) -> str:
    raw = f"{name}-{uuid.uuid4()}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    return f"STS-{digest}"


def _serialize(t: Tourist) -> dict:
    """Explicit field list -- `t.__dict__` leaked `_sa_instance_state` and would
    silently expose any future column added to the model."""
    return {
        "id": t.id,
        "digital_id": t.digital_id,
        "full_name": t.full_name,
        "nationality": t.nationality,
        "document_type": t.document_type,
        "document_number": t.document_number,
        "phone": t.phone,
        "photo": t.photo,
        "hotel": t.hotel,
        "itinerary": json.loads(t.itinerary or "[]"),
        "emergency_contacts": json.loads(t.emergency_contacts or "[]"),
        "trip_start": t.trip_start,
        "trip_end": t.trip_end,
        "last_lat": t.last_lat,
        "last_lng": t.last_lng,
        "last_seen": t.last_seen,
        "safety_score": t.safety_score,
        "tracking_enabled": t.tracking_enabled,
        "status": t.status,
        "is_valid": t.is_valid,
        "preferred_language": t.preferred_language,
        "data_retention_days": t.data_retention_days,
        "nationality_code": t.nationality_code,
        "visa_type": t.visa_type,
        "visa_expiry": t.visa_expiry,
        "passport_expiry": t.passport_expiry,
    }


@router.post("", response_model=TouristOut, status_code=201,
             dependencies=[Depends(registration_rate_limit)])
def register_tourist(payload: TouristCreate, db: Session = Depends(get_db)):
    """Register a tourist, mint a digital ID, and seed its hash chain."""
    digital_id = _generate_digital_id(payload.full_name)
    tourist = Tourist(
        digital_id=digital_id,
        full_name=payload.full_name,
        nationality=payload.nationality,
        nationality_code=consular.normalize_nationality(payload.nationality),
        document_type=payload.document_type,
        document_number=payload.document_number,
        phone=payload.phone,
        photo=payload.photo,
        hotel=payload.hotel,
        itinerary=json.dumps([w.model_dump() for w in payload.itinerary]),
        emergency_contacts=json.dumps([c.model_dump() for c in payload.emergency_contacts]),
        trip_start=payload.trip_start,
        trip_end=payload.trip_end,
        visa_type=payload.visa_type,
        visa_number=payload.visa_number,
        visa_expiry=payload.visa_expiry,
        passport_expiry=payload.passport_expiry,
        planned_states=json.dumps(payload.planned_states),
    )
    db.add(tourist)
    db.flush()

    # Genesis block of the tamper-proof ID chain
    hashchain.append_block(db, tourist, "ID_ISSUED", {
        "digital_id": digital_id,
        "name": payload.full_name,
        "document": payload.document_number,
        "trip_end": payload.trip_end.isoformat(),
    })

    # Reuses the same chain rather than a parallel one -- a visa record is
    # just another attested fact about this tourist's ID.
    if payload.document_type == "passport":
        hashchain.append_block(db, tourist, "VISA_RECORDED", {
            "visa_type": payload.visa_type,
            "visa_expiry": payload.visa_expiry.isoformat() if payload.visa_expiry else None,
        })

    # Mint the Digital Tourist Safety ID's secure QR token so the card is
    # ready to display immediately after registration -- see
    # services/tourist_id.py.
    tourist_id_service.issue_token(db, tourist)

    # optional tourist login account
    if payload.email and payload.password:
        if db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        db.add(User(
            email=payload.email, full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role="tourist", tourist_id=tourist.id,
        ))

    db.commit()
    db.refresh(tourist)

    # If the frontend completed the 3-step liveness check (see
    # services/liveness.py), bind that verification to this tourist now
    # that its id exists. Best-effort and silent: a missing/expired/
    # mismatched token never blocks registration, it just means this
    # tourist's photo doesn't carry the (internal-only, never exposed via
    # any API) liveness stamp.
    if payload.liveness_token:
        liveness.consume_verification(db, payload.liveness_token, payload.photo, tourist.id)

    return _serialize(tourist)


@router.post("/verify-liveness", response_model=LivenessVerifyResponse,
             dependencies=[Depends(registration_rate_limit)])
def verify_liveness(payload: LivenessVerifyRequest, db: Session = Depends(get_db)):
    """Called once the browser's 3-step head-movement check completes (or
    times out) during registration, before the tourist record exists --
    same public, rate-limited shape as POST /tourists itself. See
    services/liveness.py for exactly what is and isn't verified server-side.
    """
    return liveness.verify_liveness(db, payload)


@router.get("", response_model=list[TouristOut])
def list_tourists(response: Response, page: PageParams = Depends(),
                  db: Session = Depends(get_db), _: User = Depends(require_admin)):
    total = db.query(func.count(Tourist.id)).scalar()
    response.headers["X-Total-Count"] = str(total)
    rows = page.apply(db.query(Tourist).order_by(Tourist.id)).all()
    return [_serialize(t) for t in rows]


@router.get("/{tourist_id}", response_model=TouristOut)
def get_tourist(tourist_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    if user.role == "tourist" and user.tourist_id != tourist_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return _serialize(t)


@router.get("/by-digital-id/{digital_id}", response_model=TouristOut)
def get_by_digital_id(digital_id: str, db: Session = Depends(get_db),
                      _: User = Depends(require_admin)):
    t = db.query(Tourist).filter(Tourist.digital_id == digital_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return _serialize(t)


@router.get("/{tourist_id}/qr")
def get_qr(tourist_id: int, db: Session = Depends(get_db),
           _: User = Depends(require_self_or_admin)):
    """Return a base64 PNG QR code encoding the digital ID + validity."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    content = json.dumps({
        "digital_id": t.digital_id,
        "name": t.full_name,
        "valid_until": t.trip_end.isoformat(),
    })
    img = qrcode.make(content)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"digital_id": t.digital_id, "qr_png_base64": f"data:image/png;base64,{b64}"}


@router.get("/{tourist_id}/passport")
def get_passport(tourist_id: int, db: Session = Depends(get_db),
                 _: User = Depends(require_self_admin_or_responder)):
    """Digital Safety Passport: the essentials an emergency responder needs,
    in one view -- ID, contacts, language, device, current risk, plus a QR
    code encoding the digital ID. See services/passport.py."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return passport_service.build_passport(db, t)


@router.post("/{tourist_id}/passport/scan")
def scan_passport(tourist_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_self_admin_or_responder)):
    """Same as GET /passport, but logs the scan as a chain event -- used when
    a responder in the field scans a tourist's QR code."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    hashchain.append_block(db, t, "PASSPORT_SCANNED", {"scanned_by": user.email})
    db.commit()
    return passport_service.build_passport(db, t)


@router.get("/{tourist_id}/safety-card")
def get_safety_card(tourist_id: int, db: Session = Depends(get_db),
                    _: User = Depends(require_self_or_admin)):
    """Offline Maps & Safety Card: nearest hospital/police + emergency
    numbers -- see services/safety_card.py. Cached by the PWA service worker
    for offline use like every other GET."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return build_safety_card(db, t)


@router.get("/{tourist_id}/nearby")
def get_nearby(tourist_id: int, category: str, radius_m: float = 5000,
               db: Session = Depends(get_db), _: User = Depends(require_self_or_admin)):
    """Every hospital/police/pharmacy/transport option near the tourist's
    live location, distance-sorted -- see services/nearby.py. Real hospital/
    police data (including the committed OSM import); pharmacy/transport are
    seeded demo fixtures unless a real feed is added."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    if category not in ("hospital", "police", "pharmacy", "transport"):
        raise HTTPException(status_code=400, detail="category must be one of: hospital, police, pharmacy, transport")
    if t.last_lat is None:
        return []
    return find_nearby(db, t.last_lat, t.last_lng, category, radius_m)


@router.get("/{tourist_id}/navigation")
def get_navigation(tourist_id: int, db: Session = Depends(get_db),
                   _: User = Depends(require_self_or_admin)):
    """Voice-guidance navigation toward the tourist's next confirmed
    itinerary stop -- see services/navigation.py. The voice assistant
    (frontend) polls this and speaks `instruction` only when the tourist has
    turned voice guidance on; this endpoint itself never makes any sound."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return get_navigation_guidance(t)


@router.get("/{tourist_id}/chain", response_model=list[IdBlockOut])
def get_chain(tourist_id: int, db: Session = Depends(get_db),
              _: User = Depends(require_self_or_admin)):
    return (
        db.query(IdBlock)
        .filter(IdBlock.tourist_id == tourist_id)
        .order_by(IdBlock.index.asc())
        .all()
    )


@router.get("/{tourist_id}/chain/verify")
def verify_chain(tourist_id: int, db: Session = Depends(get_db),
                 _: User = Depends(require_self_or_admin)):
    return hashchain.verify_chain(db, tourist_id)


@router.post("/{tourist_id}/chain/tamper-demo")
def tamper_demo(tourist_id: int, block_index: int = 1, db: Session = Depends(get_db),
                _: User = Depends(require_admin)):
    """DEMO ONLY -- edit a stored block in place to prove tamper detection works.

    Disabled in production. Mutates a block's `data` without recomputing its hash,
    exactly as an attacker with database access would; `chain/verify` must then
    report the chain as broken at that index.
    """
    if settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    block = (
        db.query(IdBlock)
        .filter(IdBlock.tourist_id == tourist_id, IdBlock.index == block_index)
        .first()
    )
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    payload = json.loads(block.data or "{}")
    payload["tampered"] = "this value was injected directly into the database"
    block.data = json.dumps(payload, sort_keys=True)
    db.commit()
    return {"tampered_block": block_index,
            "verify": hashchain.verify_chain(db, tourist_id)}


@router.post("/{tourist_id}/location")
def update_location(tourist_id: int, payload: LocationUpdate, db: Session = Depends(get_db),
                    _: User = Depends(require_self_or_admin)):
    """Ingest a GPS ping through the full monitoring pipeline."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return process_ping(db, t, payload.lat, payload.lng, payload.speed_kmh)


@router.get("/{tourist_id}/safety-score", response_model=SafetyScoreOut)
def get_safety_score(tourist_id: int, db: Session = Depends(get_db),
                     _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    last = (
        db.query(LocationPing)
        .filter(LocationPing.tourist_id == tourist_id)
        .order_by(LocationPing.timestamp.desc())
        .first()
    )
    anomaly_score = last.anomaly_score if last and last.anomaly_score is not None else 0.1
    result = compute_safety_score(db, t, anomaly_score=anomaly_score)
    return SafetyScoreOut(tourist_id=tourist_id, **result)


@router.post("/{tourist_id}/tracking")
def toggle_tracking(tourist_id: int, enabled: bool, db: Session = Depends(get_db),
                    _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    t.tracking_enabled = enabled
    db.commit()
    return {"tourist_id": tourist_id, "tracking_enabled": enabled}


@router.get("/{tourist_id}/pings")
def get_pings(tourist_id: int, limit: int = 100, db: Session = Depends(get_db),
              _: User = Depends(require_self_or_admin)):
    pings = (
        db.query(LocationPing)
        .filter(LocationPing.tourist_id == tourist_id)
        .order_by(LocationPing.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        {"lat": p.lat, "lng": p.lng, "speed_kmh": p.speed_kmh,
         "timestamp": p.timestamp.isoformat(), "is_anomaly": p.is_anomaly,
         "anomaly_score": p.anomaly_score}
        for p in reversed(pings)
    ]


@router.get("/{tourist_id}/trajectory-forecast")
def get_trajectory_forecast(tourist_id: int, horizon_min: float = 15.0,
                            db: Session = Depends(get_db),
                            _: User = Depends(require_self_or_admin)):
    """Predicted future positions (kinematic extrapolation from recent pings),
    plus a warning if the projected path crosses a high-risk/restricted zone."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    pings = (
        db.query(LocationPing)
        .filter(LocationPing.tourist_id == tourist_id)
        .order_by(LocationPing.timestamp.desc())
        .limit(5)
        .all()
    )
    pings = list(reversed(pings))
    predicted = predict_trajectory(pings, horizon_min)
    zones = db.query(Zone).all()
    crossing = predicts_crosses_zone(predicted, zones) if predicted else None
    return {
        "tourist_id": tourist_id,
        "points": [{"lat": lat, "lng": lng, "eta_min": eta} for lat, lng, eta in predicted],
        "warning": {
            "zone_id": crossing["zone"].id,
            "zone_name": crossing["zone"].name,
            "risk_level": crossing["zone"].risk_level,
            "eta_min": crossing["eta_min"],
        } if crossing else None,
    }


@router.get("/{tourist_id}/risk-forecast")
def get_risk_forecast(tourist_id: int, db: Session = Depends(get_db),
                      _: User = Depends(require_self_or_admin)):
    """Dynamic risk forecast: predicted safety score at +15/+30/+60 minutes."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return {"tourist_id": tourist_id, "forecast": forecast_risk(db, t, DEFAULT_HORIZONS_MIN)}


@router.get("/{tourist_id}/route-recommendation")
def get_route_recommendation(tourist_id: int, dest_lat: float, dest_lng: float,
                             db: Session = Depends(get_db),
                             _: User = Depends(require_self_or_admin)):
    """Approximate, lower-risk route from the tourist's last known position to
    a destination. NOT turn-by-turn navigation -- see `app.services.routing`
    for why (no road-network routing engine in this codebase)."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    if t.last_lat is None or t.last_lng is None:
        raise HTTPException(status_code=400, detail="Tourist has no known location yet")
    result = recommend_route(db, (t.last_lat, t.last_lng), (dest_lat, dest_lng))
    return {"tourist_id": tourist_id, **result}


# ---------------- check-in / check-out ----------------
@router.post("/{tourist_id}/checkins", response_model=CheckInOut, status_code=201)
def create_checkin(tourist_id: int, payload: CheckInCreate, db: Session = Depends(get_db),
                   _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    c = CheckIn(tourist_id=tourist_id, **payload.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/{tourist_id}/checkins", response_model=list[CheckInOut])
def list_checkins(tourist_id: int, db: Session = Depends(get_db),
                  _: User = Depends(require_self_or_admin)):
    return (
        db.query(CheckIn)
        .filter(CheckIn.tourist_id == tourist_id)
        .order_by(CheckIn.expected_return_at.desc())
        .all()
    )


@router.post("/{tourist_id}/checkins/{checkin_id}/checkin", response_model=CheckInOut)
def mark_checked_in(tourist_id: int, checkin_id: int, db: Session = Depends(get_db),
                    _: User = Depends(require_self_or_admin)):
    """The tourist confirming they're safely back -- clears the check-in
    before it can ever be flagged as missed. See services/checkin.py."""
    c = db.query(CheckIn).filter(CheckIn.id == checkin_id, CheckIn.tourist_id == tourist_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Check-in not found")
    if c.status not in ("planned", "missed"):
        raise HTTPException(status_code=400, detail=f"Check-in already {c.status}")
    c.checked_in_at = utc_now()
    c.status = "checked_in"
    db.commit()
    db.refresh(c)
    return c


# ---------------- privacy & consent ----------------
@router.get("/{tourist_id}/privacy")
def get_privacy(tourist_id: int, db: Session = Depends(get_db),
                _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return privacy.privacy_report(db, t)


@router.patch("/{tourist_id}/privacy")
def update_privacy(tourist_id: int, payload: PrivacySettingsUpdate, db: Session = Depends(get_db),
                   _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(t, field, value)
    db.commit()
    return privacy.privacy_report(db, t)


@router.delete("/{tourist_id}/location-history")
def delete_location_history(tourist_id: int, request: Request, db: Session = Depends(get_db),
                            user: User = Depends(require_self_or_admin)):
    """Tourist-initiated purge -- "delete my data now." See services/privacy.py."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    deleted = privacy.purge_location_history(db, t)
    audit.record(db, "purge_location_history", actor=user.email, target=t.digital_id,
                detail=f"{deleted} pings deleted", request=request)
    return {"tourist_id": tourist_id, "pings_deleted": deleted}


# ---------------- silent / duress SOS ----------------
@router.post("/{tourist_id}/duress-pin")
def set_duress_pin(tourist_id: int, payload: DuressPinSet, db: Session = Depends(get_db),
                   _: User = Depends(require_self_or_admin)):
    """Set (or replace) the PIN that raises a silent SOS -- see
    POST /tourists/{id}/sos/duress in app/api/incidents.py."""
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    t.duress_pin_hash = hash_password(payload.pin)
    db.commit()
    return {"tourist_id": tourist_id, "duress_pin_set": True}
