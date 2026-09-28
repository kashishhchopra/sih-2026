"""Permit & E-Pass Automation: pre-fills a permit/e-pass application from the
tourist's own KYC + itinerary (same "extract, then let them confirm" shape as
services/itinerary_extract.py).

Honesty rule (this app has no official government integration for any of
these permits): this module NEVER submits anything to a government system,
and never claims to. "Confirm" only (a) locks in a local draft the tourist
has reviewed and (b) hands back the real official portal URL where the
tourist completes the actual submission themselves. The reference number
generated here is explicitly a *local tracking id*, never presented as a
government-issued permit number.
"""
from __future__ import annotations

import json
import secrets

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.permit import Permit
from app.models.tourist import Tourist
from app.models.zone import Zone

# Catalogue of permit types this feature can help pre-fill, with the real
# official portal the tourist finishes the actual application on. India has
# no single unified national permit portal -- each maps to the correct
# real authority for the case this deployment's zones actually cover
# (Assam / Northeast India); a deployment covering other states should point
# these at that region's equivalent official portal.
PERMIT_TYPES: list[dict] = [
    {
        "code": "inner_line_permit",
        "name": "Inner Line Permit (ILP)",
        "description": "Required for Indian citizens visiting certain protected Northeastern states "
                        "(Arunachal Pradesh, Nagaland, Mizoram, Manipur).",
        "typical_processing": "1-3 days (offline); instant e-ILP for some states.",
        "portal_name": "Nagaland ILP Portal",
        "portal_url": "https://ilp.nagaland.gov.in/",
    },
    {
        "code": "protected_area_permit",
        "name": "Protected Area Permit (PAP) / Restricted Area Permit (RAP)",
        "description": "Required for foreign nationals visiting protected/restricted areas near "
                        "international borders (incl. parts of Assam, Arunachal Pradesh, Sikkim, and others).",
        "typical_processing": "3-5 working days via the FRRO.",
        "portal_name": "e-FRRO (Ministry of Home Affairs)",
        "portal_url": "https://indianfrro.gov.in/efrro/home",
    },
    {
        "code": "restricted_area_permit",
        "name": "Restricted Area Permit",
        "description": "Required for entry into zones flagged 'restricted' on the risk map.",
        "typical_processing": "5-7 working days via the FRRO.",
        "portal_name": "e-FRRO (Ministry of Home Affairs)",
        "portal_url": "https://indianfrro.gov.in/efrro/home",
    },
    {
        "code": "forest_entry_permit",
        "name": "Forest Entry Permit",
        "description": "Required for trekking/entry into reserved forest areas in Assam.",
        "typical_processing": "Same-day at the forest checkpoint, or online via Sewa Setu.",
        "portal_name": "Sewa Setu (Government of Assam)",
        "portal_url": "https://sewasetu.assam.gov.in/",
    },
    {
        "code": "wildlife_sanctuary_permit",
        "name": "Wildlife Sanctuary / National Park Entry Permit",
        "description": "Required for safari/entry into a wildlife sanctuary or national park (e.g. Kaziranga).",
        "typical_processing": "Same-day online e-permit, subject to daily visitor quota.",
        "portal_name": "Sewa Setu (Government of Assam)",
        "portal_url": "https://sewasetu.assam.gov.in/",
    },
]
_VALID_CODES = {p["code"] for p in PERMIT_TYPES}
_BY_CODE = {p["code"]: p for p in PERMIT_TYPES}


def required_for_zone(zone: Zone | None) -> list[str]:
    """Which permit types a zone's risk level suggests -- a hint shown to the
    tourist, not an enforced legal requirement (no live government registry
    to check against)."""
    if zone is None:
        return []
    if zone.risk_level == "restricted":
        return ["restricted_area_permit"]
    if zone.risk_level == "high":
        return ["forest_entry_permit", "wildlife_sanctuary_permit"]
    return []


def _prefill_form(tourist: Tourist, permit_type: str, destination_name: str) -> dict:
    itinerary = json.loads(tourist.itinerary or "[]")
    return {
        "applicant_name": tourist.full_name,
        "nationality": tourist.nationality,
        "document_type": tourist.document_type,
        "document_number": tourist.document_number,
        "phone": tourist.phone,
        "permit_type": permit_type,
        "destination": destination_name or (itinerary[0]["name"] if itinerary else ""),
        "trip_start": tourist.trip_start.date().isoformat(),
        "trip_end": tourist.trip_end.date().isoformat(),
        "purpose": "Tourism",
    }


def create_permit(
    db: Session, tourist: Tourist, permit_type: str, zone_id: int | None, destination_name: str,
) -> Permit:
    """Create a draft application, pre-filled from the tourist's own record.
    Nothing is submitted anywhere -- see confirm_and_get_portal for the only
    thing "confirming" a permit actually does."""
    if permit_type not in _VALID_CODES:
        raise ValueError(f"Unknown permit type: {permit_type}")

    zone = db.get(Zone, zone_id) if zone_id else None
    form = _prefill_form(tourist, permit_type, destination_name or (zone.name if zone else ""))
    permit = Permit(
        tourist_id=tourist.id, zone_id=zone_id, permit_type=permit_type,
        destination_name=form["destination"], form_json=json.dumps(form),
        status="draft",
    )
    db.add(permit)
    db.flush()
    return permit


def update_form(db: Session, permit: Permit, form: dict) -> Permit:
    """The tourist edits the pre-filled form before confirming -- same
    "extract, then correct" pattern as the itinerary upload flow. Only a
    draft may be edited; a confirmed one is a record of what was reviewed."""
    if permit.status != "draft":
        raise ValueError("Only a draft application can be edited.")
    permit.form_json = json.dumps(form)
    db.flush()
    return permit


def confirm_and_get_portal(db: Session, permit: Permit) -> Permit:
    """The tourist has reviewed the pre-filled form and explicitly confirmed
    it. This does NOT submit anything to any government system -- there is no
    such integration. It only (a) locks the draft with a LOCAL tracking id
    (never a government reference number) and (b) records that the tourist
    was handed the real official portal to finish the actual submission on
    on their own. The frontend opens `portal_url` in a new tab right after
    this call."""
    if permit.status != "draft":
        raise ValueError("This application has already been reviewed.")
    now = utc_now()
    permit.status = "reviewed"
    permit.submitted_at = now
    permit.reference_no = f"MUSAFIR-REF-{now.year}-{secrets.token_hex(3).upper()}"
    db.flush()
    return permit


def portal_for(permit: Permit) -> dict:
    return _BY_CODE.get(permit.permit_type, {})


def serialize(permit: Permit) -> dict:
    return {
        "id": permit.id, "tourist_id": permit.tourist_id, "zone_id": permit.zone_id,
        "permit_type": permit.permit_type, "destination_name": permit.destination_name,
        "form": json.loads(permit.form_json or "{}"), "status": permit.status,
        "reference_no": permit.reference_no, "created_at": permit.created_at,
        "submitted_at": permit.submitted_at, "decided_at": permit.decided_at,
        "portal": portal_for(permit),
    }
