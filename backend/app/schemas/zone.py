from pydantic import BaseModel, Field, field_validator


class ZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    risk_level: str = Field("medium", pattern="^(low|medium|high|restricted)$")
    polygon: list[list[float]] = Field(..., min_length=3, max_length=100)  # [[lat, lng], ...]
    crime_index: float = Field(30.0, ge=0, le=100)
    description: str = Field("", max_length=1000)

    @field_validator("polygon")
    @classmethod
    def _valid_polygon(cls, v: list[list[float]]) -> list[list[float]]:
        for pt in v:
            if len(pt) != 2:
                raise ValueError("Each polygon vertex must be [lat, lng]")
            lat, lng = pt
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                raise ValueError("Polygon vertex out of valid lat/lng range")
        return v


class ZoneOut(BaseModel):
    id: int
    name: str
    risk_level: str
    polygon: list[list[float]]
    crime_index: float
    description: str
    source: str

    class Config:
        from_attributes = True
