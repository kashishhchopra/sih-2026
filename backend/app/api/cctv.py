"""CCTV network endpoints for the Police Network Dashboard.

Thin wrappers over services/cctv.py, which owns every decision that matters
(probing a real stream rather than trusting the stored row, stripping
credentials, resolving the responsible station). Access is restricted to the
same admin/responder roles the rest of the police network uses -- camera
feeds are not public.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_admin_or_responder
from app.services import audit
from app.db.session import get_db
from app.models.police import Camera
from app.models.user import User
from app.schemas.cctv import (
    CctvCameraOut,
    CctvNetworkOut,
    CctvRefreshOut,
    CctvStatusOut,
)
from app.services import cctv

router = APIRouter(prefix="/cctv", tags=["cctv"])


@router.get("", response_model=CctvNetworkOut)
def list_cctv(
    q: str | None = Query(None, max_length=200),
    station_id: int | None = None,
    zone_id: int | None = None,
    connection: str | None = Query(None, max_length=32),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_or_responder),
):
    """The whole camera network, filtered server-side.

    An empty list is a legitimate answer (no cameras registered and no
    provider configured) -- the dashboard renders "no feeds available"
    rather than being handed something invented to fill the grid.
    """
    cameras = cctv.list_cameras(
        db, q=q, station_id=station_id, zone_id=zone_id, connection=connection,
    )
    return {"cameras": cameras, "summary": cctv.network_summary(db, cameras)}


@router.get("/{camera_id}", response_model=CctvCameraOut)
def get_cctv(camera_id: int, db: Session = Depends(get_db),
             _: User = Depends(require_admin_or_responder)):
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cctv.serialize(db, cam)


@router.get("/{camera_id}/status", response_model=CctvStatusOut)
def get_cctv_status(camera_id: int, force: bool = False, db: Session = Depends(get_db),
                    _: User = Depends(require_admin_or_responder)):
    """Re-check one camera. `force=true` skips the status cache -- what the
    dashboard's Retry button calls after a failed connection."""
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    state = cctv.camera_status(db, cam, force=force)
    return {"id": cam.id, "connection": state, "last_checked_at": cam.stream_checked_at}


@router.post("/refresh", response_model=CctvRefreshOut)
def refresh_cctv(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Re-import camera metadata from the configured external provider.

    Reports `configured: false` when no provider is set up, instead of
    pretending an import happened.
    """
    return cctv.import_from_provider(db)


@router.delete("/{camera_id}", status_code=204)
def delete_cctv(camera_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_admin)):
    """Remove a camera from the directory -- for one that will never carry a
    usable feed (a dead source, a stale/incorrect registration) rather than
    leaving it cluttering the console. Admin-only, same as every other
    write on the police network."""
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    label = cam.label
    db.delete(cam)
    db.commit()
    audit.record(db, "cctv.delete", actor=user.email, target=str(camera_id),
                detail=f"Removed camera {label!r}")
