"""External Hash-Chain Anchoring: periodic external publication of the
tamper-evident chain's current root fingerprint, so integrity can be
verified by anyone -- not just trusted on the operator's word. See
services/anchoring.py.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class ChainAnchor(Base):
    __tablename__ = "chain_anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Root fingerprint: HMAC-SHA256 over every tourist chain's latest block
    # hash, sorted by tourist id -- see services/anchoring.py:compute_root().
    root_hash: Mapped[str] = mapped_column(String, nullable=False)
    tourist_count: Mapped[int] = mapped_column(Integer, default=0)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    # Where this root was published externally. "local" (the default,
    # mock-compatible backend -- see services/anchoring.py) or a real
    # external timestamping service's identifier/URL once one is configured.
    anchor_target: Mapped[str] = mapped_column(String, default="local")
    external_ref: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
