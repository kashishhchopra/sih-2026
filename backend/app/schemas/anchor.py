from datetime import datetime

from pydantic import BaseModel


class ChainAnchorOut(BaseModel):
    id: int
    root_hash: str
    tourist_count: int
    block_count: int
    anchor_target: str
    external_ref: str
    created_at: datetime

    class Config:
        from_attributes = True
