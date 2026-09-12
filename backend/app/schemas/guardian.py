from datetime import datetime

from pydantic import BaseModel, Field


class TripGuardianCreate(BaseModel):
    guardian_name: str = Field(..., min_length=1, max_length=100)
    guardian_contact: str = Field("", max_length=100)


class TripGuardianOut(BaseModel):
    id: int
    token: str
    guardian_name: str
    guardian_contact: str
    revoked: bool
    created_at: datetime

    class Config:
        from_attributes = True
