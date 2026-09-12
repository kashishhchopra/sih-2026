"""Schemas for Permit / E-Pass Automation (app/api/permits.py)."""
from datetime import datetime

from pydantic import BaseModel, Field


class PermitTypeOut(BaseModel):
    code: str
    name: str
    description: str
    typical_processing: str
    portal_name: str
    portal_url: str


class PermitCreateRequest(BaseModel):
    permit_type: str = Field(..., min_length=1, max_length=64)
    zone_id: int | None = None
    destination_name: str = Field("", max_length=120)


class PermitFormUpdate(BaseModel):
    form: dict


class PermitOut(BaseModel):
    id: int
    tourist_id: int
    zone_id: int | None
    permit_type: str
    destination_name: str
    form: dict
    status: str
    reference_no: str | None
    created_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None
    portal: dict = Field(default_factory=dict)
