"""External Hash-Chain Anchoring.

Periodically publishes a single root fingerprint of every tourist's
tamper-evident ID chain to a store outside the primary database, so a
verifier can later confirm the chain existed unchanged at that time without
needing DB access -- upgrading the tamper-evidence story from "trust us, we
checked" to "anyone can verify."

Same pluggable-backend shape as services/notifications.py: "local" (the
default) appends to an append-only JSON-lines ledger file on disk, standing
in for a real external timestamping service/public ledger, which a real
deployment would swap in behind `_publish_external()` without touching
anything else here -- the root computation, the DB record, and verification
logic are all backend-agnostic.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utc_now
from app.models.anchor import ChainAnchor
from app.models.tourist import IdBlock, Tourist

logger = get_logger(__name__)


def compute_root(db: Session) -> tuple[str, int, int]:
    """HMAC-SHA256 over every tourist chain's latest block hash, sorted by
    tourist id for a reproducible root. Returns (root_hash, tourist_count,
    block_count)."""
    tourists = db.query(Tourist.id).order_by(Tourist.id).all()
    parts = []
    block_count = 0
    for (tid,) in tourists:
        last = (
            db.query(IdBlock)
            .filter(IdBlock.tourist_id == tid)
            .order_by(IdBlock.index.desc())
            .first()
        )
        if last is None:
            continue
        parts.append(f"{tid}:{last.hash}")
        block_count += (last.index + 1)
    payload = "|".join(parts)
    root = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return root, len(parts), block_count


def _ledger_path() -> str:
    return settings.ANCHOR_LEDGER_PATH


def _publish_local(entry: dict) -> str:
    """Append-only local ledger standing in for an external service. Returns
    a receipt id a verifier can look for in that ledger."""
    path = _ledger_path()
    line = json.dumps(entry, sort_keys=True)
    receipt = hashlib.sha256(line.encode()).hexdigest()[:16]
    entry_with_receipt = {**entry, "receipt": receipt}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry_with_receipt, sort_keys=True) + "\n")
    return receipt


def _publish_external(entry: dict) -> str:
    """Placeholder for a real external timestamping service/public ledger.
    Not implemented -- no such provider/credential is assumed configured for
    this project; publish_anchor() falls back to the local ledger."""
    raise NotImplementedError


def publish_anchor(db: Session) -> ChainAnchor:
    """Compute the current chain root and publish it externally (or to the
    local stand-in), recording both in the DB as a queryable index."""
    root_hash, tourist_count, block_count = compute_root(db)
    entry = {
        "root_hash": root_hash, "tourist_count": tourist_count,
        "block_count": block_count, "anchored_at": utc_now().isoformat(),
    }

    target = settings.ANCHOR_TARGET
    if target == "local":
        external_ref = _publish_local(entry)
    else:
        try:
            external_ref = _publish_external(entry)
        except NotImplementedError:
            logger.warning("anchor_target_unimplemented", target=target, falling_back="local")
            target = "local"
            external_ref = _publish_local(entry)

    anchor = ChainAnchor(
        root_hash=root_hash, tourist_count=tourist_count, block_count=block_count,
        anchor_target=target, external_ref=external_ref,
    )
    db.add(anchor)
    db.commit()
    db.refresh(anchor)
    logger.info("chain_anchored", root_hash=root_hash, tourist_count=tourist_count,
               external_ref=external_ref)
    return anchor


def verify_anchor(anchor: ChainAnchor) -> dict:
    """Independent check: does the external ledger still contain exactly the
    entry this anchor claims? A real external service would be queried here
    instead of a local file -- the point being the verifier does not need
    this platform's database, only the published root + receipt."""
    if anchor.anchor_target != "local":
        return {"verified": None, "detail": f"No verifier implemented for target '{anchor.anchor_target}'."}

    path = _ledger_path()
    if not os.path.exists(path):
        return {"verified": False, "detail": "Local ledger file not found."}

    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("receipt") == anchor.external_ref and record.get("root_hash") == anchor.root_hash:
                return {"verified": True, "detail": "Ledger entry matches the anchored root exactly."}
    return {"verified": False, "detail": "No matching ledger entry found -- root may have been tampered with."}
