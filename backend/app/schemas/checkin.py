from datetime import datetime

from pydantic import BaseModel, Field


class CheckInCreate(BaseModel):
    destination_name: str = Field(..., min_length=1, max_length=120)
    dest_lat: float | None = Field(None, ge=-90, le=90)
    dest_lng: float | None = Field(None, ge=-180, le=180)
    expected_return_at: datetime


class CheckInOut(BaseModel):
    id: int
    destination_name: str
    dest_lat: float | None
    dest_lng: float | None
    expected_return_at: datetime
    checked_in_at: datetime | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
