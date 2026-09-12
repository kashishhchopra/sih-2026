"""Privacy & Consent Dashboard: what a tourist controls about their own
tracking data, and the scheduled enforcement of it.

Two things live here: an on-demand purge a tourist can trigger themselves
("delete my data now"), and a scheduled job that auto-deletes raw location
history once a tourist's own retention window has passed after their trip
ends -- the DPDP-Act-facing answer to "how long do you keep this."
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import utc_now
from app.models.tourist import LocationPing, Tourist

logger = get_logger(__name__)


def privacy_report(db: Session, tourist: Tourist) -> dict:
    ping_count = db.query(LocationPing).filter(LocationPing.tourist_id == tourist.id).count()
    purge_after = tourist.trip_end + timedelta(days=tourist.data_retention_days)
    return {
        "tracking_enabled": tourist.tracking_enabled,
        "data_retention_days": tourist.data_retention_days,
        "preferred_language": tourist.preferred_language,
        "location_pings_stored": ping_count,
        "auto_purge_at": purge_after,
    }


def purge_location_history(db: Session, tourist: Tourist) -> int:
    """Immediate, tourist-initiated deletion of all raw GPS history. Returns
    the number of pings removed. Safety-score/incident/alert records are
    untouched -- those are the operational record of what happened, not raw
    tracking data, and stay subject to normal retention."""
    deleted = (
        db.query(LocationPing)
        .filter(LocationPing.tourist_id == tourist.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def tick_retention_purge(db: Session) -> int:
    """Scheduled job: delete location history for any tourist whose trip
    ended more than `data_retention_days` ago. Runs on the same scheduler as
    the escalation tick (see app/main.py)."""
    now = utc_now()
    total_deleted = 0
    tourists = db.query(Tourist).filter(Tourist.trip_end < now).all()
    for t in tourists:
        cutoff = t.trip_end + timedelta(days=t.data_retention_days)
        if now < cutoff:
            continue
        deleted = (
            db.query(LocationPing)
            .filter(LocationPing.tourist_id == t.id)
            .delete(synchronize_session=False)
        )
        if deleted:
            logger.info("retention_purge", tourist_id=t.id, pings_deleted=deleted)
            total_deleted += deleted
    if total_deleted:
        db.commit()
    return total_deleted
