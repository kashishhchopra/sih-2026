"""Women & Solo Traveller Safety API: real sentiment/distress analysis of a
tourist-entered safety report, with automatic escalation into the existing
incident workflow when warranted. See services/sentiment.py and
services/monitoring.py:escalate_safety_report.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_self_or_admin
from app.db.session import get_db
from app.models.safety_report import SafetyReport
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.safety_report import (
    SafetyReportOut,
    SafetyReportRequest,
    SentimentPreviewOut,
    SentimentPreviewRequest,
)
from app.services import sentiment as sentiment_service
from app.services.monitoring import escalate_safety_report

router = APIRouter(tags=["safety-reports"])


@router.post("/sentiment/preview", response_model=SentimentPreviewOut)
def preview_sentiment(payload: SentimentPreviewRequest, _: User = Depends(get_current_user)):
    """Live-typing feedback (e.g. as the tourist writes a report) -- read-
    only, nothing is saved. Any authenticated role may call it (no
    tourist-specific data is read/written), same as /translate/*."""
    return sentiment_service.analyze(payload.text)


@router.post("/tourists/{tourist_id}/safety-reports", response_model=SafetyReportOut, status_code=201)
def create_safety_report(
    tourist_id: int, payload: SafetyReportRequest,
    db: Session = Depends(get_db), _: User = Depends(require_self_or_admin),
):
    tourist = db.get(Tourist, tourist_id)
    if not tourist:
        raise HTTPException(status_code=404, detail="Tourist not found")

    result = sentiment_service.analyze(payload.text)
    report = SafetyReport(
        tourist_id=tourist_id, text=payload.text, lat=payload.lat, lng=payload.lng,
        sentiment_label=result["label"], sentiment_score=result["score"],
        urgency=result["urgency"], distress_detected=result["distress_detected"],
    )
    db.add(report)
    db.flush()

    incident = escalate_safety_report(db, tourist, report)
    if incident:
        report.escalated_incident_id = incident.id

    db.commit()
    db.refresh(report)
    return report


@router.get("/tourists/{tourist_id}/safety-reports", response_model=list[SafetyReportOut])
def list_safety_reports(tourist_id: int, db: Session = Depends(get_db),
                        _: User = Depends(require_self_or_admin)):
    return (
        db.query(SafetyReport).filter(SafetyReport.tourist_id == tourist_id)
        .order_by(SafetyReport.created_at.desc()).all()
    )
