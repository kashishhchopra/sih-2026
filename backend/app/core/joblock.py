"""Per-job cross-worker mutual exclusion, backed by app.models.job_lock.JobLock.

A scheduled tick calls `run_locked(SessionLocal, "job_id", ttl_seconds, fn)`.
Acquisition is a single UPDATE-or-INSERT guarded by the current time, so it
works correctly under concurrent processes without a separate lock service:

- No row for this job id yet -> insert one, held.
- Row exists but `locked_until` is in the past -> another worker's hold expired
  (crashed mid-job, or just finished); steal it.
- Row exists and `locked_until` is in the future -> another worker holds it;
  skip this tick entirely.

The lock is intentionally coarse (one row per job, TTL-based, no heartbeat) --
scheduled ticks here run every 30s-30min and each does a bounded unit of work,
so "another worker already started this tick" is the only thing that needs
preventing, not fine-grained progress tracking.
"""
from __future__ import annotations

import logging
import socket
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.time import utc_now
from app.models.job_lock import JobLock

logger = logging.getLogger(__name__)

_HOLDER = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


def _try_acquire(db, job_id: str, ttl_seconds: int) -> bool:
    now = utc_now()
    row = db.execute(select(JobLock).where(JobLock.job_id == job_id)).scalar_one_or_none()
    if row is None:
        db.add(JobLock(job_id=job_id, holder=_HOLDER, locked_until=now + timedelta(seconds=ttl_seconds)))
        try:
            db.commit()
            return True
        except Exception:
            # Lost a race to insert the same job_id -- another worker got there first.
            db.rollback()
            return False
    if row.locked_until <= now:
        row.holder = _HOLDER
        row.locked_until = now + timedelta(seconds=ttl_seconds)
        db.commit()
        return True
    return False


def run_locked(session_factory: sessionmaker, job_id: str, ttl_seconds: int,
               fn: Callable[[object], None]) -> None:
    """Run `fn(db)` only if this process wins the lock for `job_id`.

    Opens its own session for the lock bookkeeping (kept separate from `fn`'s
    session so a failure inside `fn` can't leave the lock row uncommitted).
    """
    lock_db = session_factory()
    try:
        acquired = _try_acquire(lock_db, job_id, ttl_seconds)
    finally:
        lock_db.close()

    if not acquired:
        logger.debug("job_lock: skipping %s, held by another worker", job_id)
        return

    work_db = session_factory()
    try:
        fn(work_db)
    finally:
        work_db.close()
