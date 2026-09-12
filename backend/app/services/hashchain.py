"""Blockchain-style SHA-256 linked records for tamper-proof digital IDs.

Each tourist has an append-only chain of `IdBlock` rows. Every block hashes its
own contents together with the previous block's hash, so altering any historical
record invalidates every subsequent hash — exactly like a blockchain, simulated
locally for this academic project.

Verification checks two independent properties:

  1. **Content integrity** — recomputing SHA-256 over a block's own fields must
     reproduce the stored `hash`. This catches an edit to `data` or `event`.
  2. **Link integrity** — each block's `previous_hash` must equal the prior
     block's `hash`. This catches deletion, reordering, or splicing.

A tamper that fixes one property still fails the other unless every subsequent
block is also rewritten, which is the property that makes the chain evidential.

Block digests are keyed (HMAC-SHA256) with the server secret, so an attacker who
reaches the database alone cannot recompute a digest that verifies -- including
for the newest block, which no later block pins. Residual limitation: an attacker
holding BOTH the database and SECRET_KEY can rewrite the chain wholesale. Real
custody would anchor the tip hash in an external append-only store; that is out
of scope for this project and is stated here rather than glossed over.
"""
import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now_aware
from app.models.tourist import IdBlock, Tourist

GENESIS_HASH = "0" * 64


def _compute_hash(index: int, hashed_at: str, event: str, data: str,
                  previous_hash: str) -> str:
    """Keyed SHA-256 (HMAC) over the block's contents.

    A plain hash would let anyone with write access to the database edit a block
    AND recompute its hash, which defeats the whole point for the newest block in
    a chain (no later block pins it). Keying the digest with the server secret
    means a database-only compromise cannot forge a block that verifies.
    """
    payload = f"{index}|{hashed_at}|{event}|{data}|{previous_hash}"
    return hmac.new(
        settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def append_block(db: Session, tourist: Tourist, event: str, data: dict) -> IdBlock:
    """Append a new block to a tourist's hash chain and persist it."""
    last = (
        db.query(IdBlock)
        .filter(IdBlock.tourist_id == tourist.id)
        .order_by(IdBlock.index.desc())
        .first()
    )
    index = 0 if last is None else last.index + 1
    previous_hash = GENESIS_HASH if last is None else last.hash
    hashed_at = utc_now_aware().isoformat()
    data_str = json.dumps(data, sort_keys=True, default=str)
    block_hash = _compute_hash(index, hashed_at, event, data_str, previous_hash)

    block = IdBlock(
        tourist_id=tourist.id,
        index=index,
        event=event,
        data=data_str,
        previous_hash=previous_hash,
        hash=block_hash,
        hashed_at=hashed_at,
    )
    db.add(block)
    db.flush()
    return block


def verify_chain(db: Session, tourist_id: int) -> dict:
    """Recompute every hash and confirm the chain is intact (tamper detection)."""
    blocks = (
        db.query(IdBlock)
        .filter(IdBlock.tourist_id == tourist_id)
        .order_by(IdBlock.index.asc())
        .all()
    )

    previous_hash = GENESIS_HASH
    for position, b in enumerate(blocks):
        # (0) indices must be dense and ascending — catches a deleted block.
        if b.index != position:
            return {"valid": False, "blocks": len(blocks), "broken_at": position,
                    "reason": "block index gap - a record was removed or reordered"}

        # (1) content integrity: does the block still hash to what it claims?
        expected = _compute_hash(b.index, b.hashed_at or "", b.event, b.data,
                                 b.previous_hash)
        if expected != b.hash:
            return {"valid": False, "blocks": len(blocks), "broken_at": b.index,
                    "reason": "content hash mismatch - block data was altered"}

        # (2) link integrity: does it point at the real previous block?
        if b.previous_hash != previous_hash:
            return {"valid": False, "blocks": len(blocks), "broken_at": b.index,
                    "reason": "previous_hash mismatch - chain link broken"}

        previous_hash = b.hash

    return {"valid": True, "blocks": len(blocks), "broken_at": None, "reason": None}
