"""Cross-worker lock for scheduled jobs.

APScheduler (app/core/scheduler.py) runs in-process, so with WEB_CONCURRENCY > 1
each worker process runs its own copy of every scheduled job -- duplicate SOS
escalations, duplicate disaster ticks, etc. A row per job id plus a conditional
UPDATE (see app/core/joblock.py) gives mutual exclusion across processes without
needing a separate coordination service, and works the same way on SQLite (dev)
and Postgres (prod).
"""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class JobLock(Base):
    __tablename__ = "job_locks"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    holder: Mapped[str] = mapped_column(String, nullable=False)
    locked_until: Mapped[datetime] = mapped_column(DateTime, nullable=False)
