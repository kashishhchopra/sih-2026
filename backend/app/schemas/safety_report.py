"""Schemas for Women & Solo Traveller Safety reports (app/api/safety_reports.py)."""
from datetime import datetime

from pydantic import BaseModel, Field


class SafetyReportRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    lat: float | None = None
    lng: float | None = None


class SafetyReportOut(BaseModel):
    id: int
    tourist_id: int
    text: str
    lat: float | None
    lng: float | None
    sentiment_label: str
    sentiment_score: float
    urgency: str
    distress_detected: bool
    escalated_incident_id: int | None
    created_at: datetime


class SentimentPreviewRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class SentimentPreviewOut(BaseModel):
    label: str
    score: float
    urgency: str
    distress_detected: bool
    fear_signals: list[str]
    anger_signals: list[str]
    method: str
