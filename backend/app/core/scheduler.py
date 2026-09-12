"""Background job runner (APScheduler) -- first use of one in this codebase.

Single-process, in-memory scheduler: same assumption the rate limiter already
documents (see `app/core/ratelimit.py`) -- fine for a single-worker deployment,
but with WEB_CONCURRENCY > 1 each worker would run its own copy of every job.
A future multi-worker deployment should either pin the scheduler to one worker
or move to a store-backed job queue.

This module owns only start/stop of the scheduler itself. Feature-specific jobs
(e.g. the escalation tick) live in their own service module and register
themselves with `scheduler.add_job(...)` -- this file has no domain knowledge.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import STATE_STOPPED

scheduler = BackgroundScheduler()


def start() -> None:
    """Start the scheduler if it isn't already running. Safe to call twice.

    APScheduler's `shutdown()` permanently retires that instance's thread
    pool -- calling `start()` again on the same object leaves `running` True
    but every submitted job fails ("cannot schedule new futures after
    shutdown"). The test suite's `client` fixture triggers a fresh
    lifespan start/stop on every test via FastAPI's TestClient, so a stopped
    scheduler must be replaced, not merely restarted.
    """
    global scheduler
    if scheduler.state == STATE_STOPPED:
        scheduler = BackgroundScheduler()
    if not scheduler.running:
        scheduler.start()


def shutdown() -> None:
    """Stop the scheduler if it's running. Safe to call twice."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
