from datetime import datetime

from pydantic import BaseModel, Field


class AlertOut(BaseModel):
    id: int
    tourist_id: int | None
    type: str
    severity: str
    message: str
    lat: float | None
    lng: float | None
    acknowledged: bool
    created_at: datetime

    class Config:
        from_attributes = True


class IncidentEventOut(BaseModel):
    status: str
    note: str
    timestamp: datetime

    class Config:
        from_attributes = True


class IncidentOut(BaseModel):
    id: int
    tourist_id: int | None
    # Not real columns on Incident -- attached at the API layer (see
    # api/incidents.py:_hydrate_tourist_info) so the admin incidents list
    # shows whose case this is without a second round trip per row.
    tourist_name: str | None = None
    tourist_digital_id: str | None = None
    type: str
    severity: str
    status: str
    description: str
    lat: float | None
    lng: float | None
    assigned_unit_id: int | None
    station_id: int | None
    silent: bool
    escalation_stage: str
    escalation_deadline: datetime | None
    detected_at: datetime
    acknowledged_at: datetime | None
    dispatched_at: datetime | None
    resolved_at: datetime | None
    response_time_seconds: float | None
    events: list[IncidentEventOut] = []

    class Config:
        from_attributes = True


class IncidentStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(acknowledged|dispatched|resolved)$")
    note: str = Field("", max_length=1000)


class DispatchCandidateOut(BaseModel):
    unit_id: int
    name: str
    unit_type: str
    station: str
    distance_km: float
    eta_min: float
    available: bool


class SOSRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    message: str = Field("SOS - emergency assistance required", max_length=500)
    # Silent/Duress SOS: raised via a discreet trigger (shake, rapid re-press,
    # duress PIN) rather than the visible button -- same payload, tagged so
    # the control room knows not to call back or approach visibly.
    silent: bool = False


class PoliceUnitOut(BaseModel):
    id: int
    name: str
    station: str
    phone: str
    lat: float
    lng: float
    available: bool
    unit_type: str

    class Config:
        from_attributes = True


class EFIROut(BaseModel):
    id: int
    fir_number: str
    incident_id: int
    tourist_id: int
    status: str
    narrative: str
    last_known_lat: float | None
    last_known_lng: float | None
    last_seen_at: datetime | None
    document_hash: str
    filed_at: datetime
    closed_at: datetime | None

    class Config:
        from_attributes = True
