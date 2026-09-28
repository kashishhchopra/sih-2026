"""Cross-worker job lock (app/core/joblock.py, app/models/job_lock.py)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.joblock import run_locked
from app.core.time import utc_now
from app.db.session import Base
from app.models.job_lock import JobLock


def _session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_run_locked_executes_when_no_lock_held():
    Session = _session_factory()
    calls = []
    run_locked(Session, "job_a", 60, calls.append)
    assert len(calls) == 1


def test_run_locked_creates_a_lock_row():
    Session = _session_factory()
    run_locked(Session, "job_b", 60, lambda db: None)
    db = Session()
    row = db.get(JobLock, "job_b")
    db.close()
    assert row is not None
    assert row.locked_until > utc_now()


def test_run_locked_skips_when_another_worker_holds_it():
    Session = _session_factory()
    db = Session()
    db.add(JobLock(job_id="job_c", holder="other-worker", locked_until=utc_now() + timedelta(seconds=60)))
    db.commit()
    db.close()

    calls = []
    run_locked(Session, "job_c", 60, calls.append)
    assert calls == []


def test_run_locked_steals_an_expired_lock():
    Session = _session_factory()
    db = Session()
    db.add(JobLock(job_id="job_d", holder="dead-worker", locked_until=utc_now() - timedelta(seconds=1)))
    db.commit()
    db.close()

    calls = []
    run_locked(Session, "job_d", 60, calls.append)
    assert len(calls) == 1


def test_run_locked_uses_a_separate_session_for_the_work():
    """fn(db) must receive a live, usable session distinct from lock bookkeeping."""
    Session = _session_factory()
    seen = []

    def fn(db):
        seen.append(db.get(JobLock, "job_e"))

    run_locked(Session, "job_e", 60, fn)
    assert len(seen) == 1
    assert seen[0] is not None
