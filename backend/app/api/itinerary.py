"""Itinerary document upload/extraction/review/confirm, and the
itinerary-aware nearby-places lookup that reads the confirmed itinerary.

Upload -> extract -> tourist reviews/edits -> confirm -> written into the
existing Tourist.itinerary. See services/itinerary_extract.py for the
extraction/parsing this thinly wraps.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_self_admin_or_responder, require_self_or_admin
from app.core.config import settings
from app.core.time import utc_now
from app.db.session import get_db
from app.models.itinerary import ItineraryDocument
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.itinerary import ExtractedItinerary, ItineraryDocumentOut
from app.schemas.tourist import Waypoint
from app.services.itinerary_extract import ExtractionError, extract_text, parse_itinerary_text

router = APIRouter(prefix="/tourists/{tourist_id}/itinerary-documents", tags=["itinerary"])


def _get_tourist_or_404(tourist_id: int, db: Session) -> Tourist:
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    return t


def _get_document_or_404(tourist_id: int, doc_id: int, db: Session) -> ItineraryDocument:
    doc = db.get(ItineraryDocument, doc_id)
    if not doc or doc.tourist_id != tourist_id:
        raise HTTPException(status_code=404, detail="Itinerary document not found")
    return doc


def _serialize(doc: ItineraryDocument) -> dict:
    return {
        "id": doc.id, "tourist_id": doc.tourist_id, "filename": doc.filename,
        "content_type": doc.content_type, "uploaded_at": doc.uploaded_at,
        "status": doc.status, "error": doc.error,
        "extracted": json.loads(doc.extracted_json or "{}"),
        "confirmed": doc.confirmed, "confirmed_at": doc.confirmed_at,
    }


@router.post("", response_model=ItineraryDocumentOut, status_code=201)
async def upload_itinerary_document(
    tourist_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
    _: User = Depends(require_self_or_admin),
):
    """Upload a PDF/DOCX/text itinerary. Extraction runs synchronously and
    always returns 201 -- a failed extraction still creates the document
    (status="failed", `error` explains why) so the tourist lands on the
    review page with a clear reason and a blank form to fill in by hand,
    never a dead end."""
    _get_tourist_or_404(tourist_id, db)
    content = await file.read()
    if len(content) > settings.ITINERARY_DOCUMENT_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {settings.ITINERARY_DOCUMENT_MAX_BYTES // 1_000_000} MB).",
        )

    doc = ItineraryDocument(
        tourist_id=tourist_id, filename=file.filename or "itinerary",
        content_type=file.content_type or "",
    )
    try:
        text = extract_text(doc.filename, content, doc.content_type)
        extracted = parse_itinerary_text(text)
        doc.extracted_json = json.dumps(extracted, default=str)
        doc.status = "extracted"
    except ExtractionError as e:
        doc.status = "failed"
        doc.error = str(e)
        doc.extracted_json = json.dumps(ExtractedItinerary().model_dump(), default=str)

    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _serialize(doc)


@router.get("", response_model=list[ItineraryDocumentOut])
def list_itinerary_documents(tourist_id: int, db: Session = Depends(get_db),
                             _: User = Depends(require_self_admin_or_responder)):
    _get_tourist_or_404(tourist_id, db)
    docs = (
        db.query(ItineraryDocument)
        .filter(ItineraryDocument.tourist_id == tourist_id)
        .order_by(ItineraryDocument.uploaded_at.desc())
        .all()
    )
    return [_serialize(d) for d in docs]


@router.get("/{doc_id}", response_model=ItineraryDocumentOut)
def get_itinerary_document(tourist_id: int, doc_id: int, db: Session = Depends(get_db),
                           _: User = Depends(require_self_admin_or_responder)):
    _get_tourist_or_404(tourist_id, db)
    return _serialize(_get_document_or_404(tourist_id, doc_id, db))


@router.patch("/{doc_id}", response_model=ItineraryDocumentOut)
def edit_extracted_itinerary(tourist_id: int, doc_id: int, payload: ExtractedItinerary,
                             db: Session = Depends(get_db),
                             _: User = Depends(require_self_or_admin)):
    """The tourist corrects whatever the heuristic parser got wrong before
    confirming -- extraction is never assumed to be perfect."""
    _get_tourist_or_404(tourist_id, db)
    doc = _get_document_or_404(tourist_id, doc_id, db)
    doc.extracted_json = payload.model_dump_json()
    db.commit()
    db.refresh(doc)
    return _serialize(doc)


@router.post("/{doc_id}/confirm", response_model=ItineraryDocumentOut)
def confirm_itinerary_document(tourist_id: int, doc_id: int, db: Session = Depends(get_db),
                               _: User = Depends(require_self_or_admin)):
    """Write the (possibly edited) destination sequence into the tourist's
    real itinerary (Tourist.itinerary, the field the map/geofence/AI copilot
    already read from) -- only destinations we could place a coordinate for
    make it in; unplaced ones stay visible on this document's own extracted
    list but don't silently get a fabricated location."""
    t = _get_tourist_or_404(tourist_id, db)
    doc = _get_document_or_404(tourist_id, doc_id, db)

    extracted = ExtractedItinerary.model_validate_json(doc.extracted_json or "{}")
    waypoints = [
        Waypoint(name=d.name, lat=d.lat, lng=d.lng)
        for d in extracted.destinations if d.lat is not None and d.lng is not None
    ]
    if waypoints:
        t.itinerary = json.dumps([w.model_dump() for w in waypoints])

    doc.confirmed = True
    doc.confirmed_at = utc_now()
    db.commit()
    db.refresh(doc)
    return _serialize(doc)
