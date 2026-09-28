"""Structured (JSON) logging.

Plain `print()`/default logging gives you unparseable text and no way to trace
one request's log lines from another once traffic is concurrent. Every line
here carries a request id (bound by RequestIDMiddleware below) so a single
incident -- e.g. "why was this alert raised" -- can be grepped end to end
across the monitoring pipeline, not just the endpoint that returned first.
"""
from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def configure_logging(json_output: bool) -> None:
    """Call once at startup. `json_output=False` gives readable console output
    for local dev; `True` gives one JSON object per line for log aggregators."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamp every request/response with an id, and bind it into structlog's
    context so every log line emitted while handling this request carries it
    automatically -- no need to thread a request object through every service
    function just to log a correlation id."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming or uuid.uuid4().hex[:16]
        token = _request_id_ctx.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
            _request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


def current_request_id() -> str:
    return _request_id_ctx.get()
