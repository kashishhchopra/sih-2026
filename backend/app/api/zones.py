import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.zone import Zone
from app.schemas.zone import ZoneCreate, ZoneOut
from app.services import crowd_density, geo

router = APIRouter(prefix="/zones", tags=["zones"])


def _serialize(z: Zone) -> dict:
    return {
        "id": z.id, "name": z.name, "risk_level": z.risk_level,
        "polygon": json.loads(z.polygon), "crime_index": z.crime_index,
        "description": z.description, "source": z.source,
    }


@router.get("", response_model=list[ZoneOut])
def list_zones(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [_serialize(z) for z in db.query(Zone).all()]


@router.post("", response_model=ZoneOut, status_code=201)
def create_zone(payload: ZoneCreate, db: Session = Depends(get_db),
                _: User = Depends(require_admin)):
    z = Zone(
        name=payload.name, risk_level=payload.risk_level,
        polygon=json.dumps(payload.polygon), crime_index=payload.crime_index,
        description=payload.description, source="manual",
    )
    db.add(z)
    db.commit()
    db.refresh(z)
    return _serialize(z)


@router.get("/crowd-density")
def crowd_density_report(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Per-zone tourist concentration -- overcrowding is its own kind of risk.
    See services/crowd_density.py."""
    return crowd_density.zone_density_report(db)


@router.delete("/{zone_id}", status_code=204)
def delete_zone(zone_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    z = db.get(Zone, zone_id)
    if not z:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(z)
    db.commit()
    geo.clear_polygon_cache()
