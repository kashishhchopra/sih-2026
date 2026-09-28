"""Auto-generate an E-FIR (First Information Report) draft for missing tourists."""
import json

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.alert import Alert
from app.models.efir import EFIR
from app.models.incident import Incident
from app.models.tourist import Tourist
from app.services import efir_pdf, hashchain


def generate_efir(db: Session, tourist: Tourist) -> dict:
    """Fill an E-FIR template from tourist KYC + last location + anomaly timeline."""
    contacts = json.loads(tourist.emergency_contacts or "[]")
    itinerary = json.loads(tourist.itinerary or "[]")

    anomaly_alerts = (
        db.query(Alert)
        .filter(Alert.tourist_id == tourist.id)
        .order_by(Alert.created_at.asc())
        .all()
    )
    timeline = [
        {
            "time": a.created_at.isoformat(),
            "type": a.type,
            "severity": a.severity,
            "message": a.message,
            "lat": a.lat,
            "lng": a.lng,
        }
        for a in anomaly_alerts
    ]

    now = utc_now()
    fir_no = f"EFIR/{now.year}/{tourist.id:05d}"

    narrative = (
        f"This E-FIR is auto-generated for missing person {tourist.full_name} "
        f"(Digital Tourist ID: {tourist.digital_id}, {tourist.document_type.upper()} "
        f"No: {tourist.document_number}). The tourist was last seen at coordinates "
        f"({tourist.last_lat}, {tourist.last_lng}) on "
        f"{tourist.last_seen.isoformat() if tourist.last_seen else 'unknown'}. "
        f"The MUSAFIR system recorded {len(timeline)} anomaly/alert event(s) "
        f"prior to loss of contact. Immediate search and rescue is recommended."
    )

    return {
        "fir_number": fir_no,
        "generated_at": now.isoformat(),
        "status": "DRAFT",
        "subject": {
            "name": tourist.full_name,
            "nationality": tourist.nationality,
            "document_type": tourist.document_type,
            "document_number": tourist.document_number,
            "phone": tourist.phone,
            "digital_id": tourist.digital_id,
        },
        "trip": {
            "start": tourist.trip_start.isoformat(),
            "end": tourist.trip_end.isoformat(),
            "itinerary": itinerary,
        },
        "last_known_location": {
            "lat": tourist.last_lat,
            "lng": tourist.last_lng,
            "seen_at": tourist.last_seen.isoformat() if tourist.last_seen else None,
        },
        "emergency_contacts": contacts,
        "anomaly_timeline": timeline,
        "narrative": narrative,
    }


def file_efir(db: Session, incident: Incident, tourist: Tourist) -> EFIR:
    """Persist and file an EFIR for a missing-person incident.

    Filing does three things atomically: writes the EFIR row, computes its
    content hash, and appends that hash to the tourist's own tamper-evident ID
    chain as an EFIR_FILED block -- so the filing itself becomes part of the
    same evidence trail as the digital ID, and a later edit to the stored
    narrative is detectable the same way a forged ID block would be.
    """
    preview = generate_efir(db, tourist)
    fir_number = f"{preview['fir_number']}-{incident.id}"

    efir = EFIR(
        fir_number=fir_number,
        incident_id=incident.id,
        tourist_id=tourist.id,
        narrative=preview["narrative"],
        last_known_lat=tourist.last_lat,
        last_known_lng=tourist.last_lng,
        last_seen_at=tourist.last_seen,
        document_hash="",  # filled below, once the row has its final field values
    )
    db.add(efir)
    db.flush()

    efir.document_hash = efir_pdf.compute_document_hash(efir, tourist)
    db.flush()

    hashchain.append_block(db, tourist, "EFIR_FILED", {
        "fir_number": efir.fir_number,
        "incident_id": incident.id,
        "document_hash": efir.document_hash,
    })
    return efir
