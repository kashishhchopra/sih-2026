"""IoT smart-band device management and telemetry ingestion."""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import authenticate_device, require_admin
from app.core.security import hash_password
from app.core.time import utc_now
from app.db.session import get_db
from app.models.device import Device
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.device import DeviceOut, DeviceRegister, DeviceRegistered, DeviceTelemetry
from app.services.monitoring import process_device_telemetry

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("/register", response_model=DeviceRegistered, status_code=201)
def register_device(payload: DeviceRegister, db: Session = Depends(get_db),
                    _: User = Depends(require_admin)):
    """Provision a band for a tourist and return its one-time API key.

    The key is returned exactly once, at creation time -- only its bcrypt hash
    is persisted, the same handling as a user password.
    """
    if not db.get(Tourist, payload.tourist_id):
        raise HTTPException(status_code=404, detail="Tourist not found")
    if db.query(Device).filter(Device.device_id == payload.device_id).first():
        raise HTTPException(status_code=400, detail="device_id already registered")

    api_key = secrets.token_urlsafe(32)
    device = Device(
        device_id=payload.device_id, tourist_id=payload.tourist_id,
        firmware_version=payload.firmware_version,
        hashed_key=hash_password(api_key),
    )
    db.add(device)
    db.commit()
    return DeviceRegistered(device_id=device.device_id, api_key=api_key,
                            tourist_id=payload.tourist_id)


@router.get("", response_model=list[DeviceOut])
def list_devices(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return db.query(Device).all()


@router.post("/{device_id}/telemetry")
def submit_telemetry(payload: DeviceTelemetry, db: Session = Depends(get_db),
                     device: Device = Depends(authenticate_device)):
    """Ingest one telemetry frame from a band. Authenticated by device key, not
    a user JWT -- see app/api/deps.py:authenticate_device."""
    tourist = db.get(Tourist, device.tourist_id)
    if not tourist:
        raise HTTPException(status_code=404, detail="Linked tourist not found")

    device.last_heartbeat = utc_now()
    if payload.battery_pct is not None:
        device.battery_pct = payload.battery_pct
    db.commit()

    return process_device_telemetry(
        db, tourist, payload.lat, payload.lng, payload.speed_kmh,
        payload.heart_rate_bpm, payload.sos_pressed, payload.fall_detected,
    )


@router.post("/{device_id}/deactivate")
def deactivate_device(device_id: str, db: Session = Depends(get_db),
                      _: User = Depends(require_admin)):
    """Revoke a lost/decommissioned band without deleting its history."""
    device = db.query(Device).filter(Device.device_id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.active = False
    db.commit()
    return {"device_id": device_id, "active": False}
