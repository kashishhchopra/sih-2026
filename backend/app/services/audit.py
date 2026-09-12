"""Helper to record audit-log entries. Never raises into the request path.

The audit trail deliberately uses its OWN database session. It previously called
`db.commit()` on the caller's session, which committed whatever else that request
had staged -- e.g. in `mark_missing` the tourist's status change was committed
before the incident row was created, so a failure in between left the database in
a state the workflow never intended. An independent session means an audit write
can neither commit nor roll back the caller's transaction.
"""
from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

# Indirection so tests (and any future multi-database setup) can point the audit
# trail at a different engine. Calling SessionLocal directly would bypass the
# app's dependency overrides and write to the real database during tests.
_session_factory = SessionLocal


def set_session_factory(factory) -> None:
    """Override the session factory used for audit writes."""
    global _session_factory
    _session_factory = factory


def reset_session_factory() -> None:
    global _session_factory
    _session_factory = SessionLocal


def _ip(request: Request | None) -> str:
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def record(db: Session | None = None, action: str = "", actor: str = "anonymous",
           target: str = "", detail: str = "", outcome: str = "success",
           request: Request | None = None) -> None:
    """Write one audit row in its own transaction.

    `db` is accepted and ignored for call-site compatibility; auditing must not
    share the caller's transaction.
    """
    session = _session_factory()
    try:
        session.add(AuditLog(
            actor=actor, action=action, target=target,
            detail=detail, outcome=outcome, ip=_ip(request),
        ))
        session.commit()
    except Exception:  # noqa: BLE001 -- auditing must never break the request
        session.rollback()
        logger.exception("Failed to write audit log entry for action=%s", action)
    finally:
        session.close()
