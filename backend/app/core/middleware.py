"""Security middleware: hardening headers and a request body-size guard."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings

# A conservative CSP. The API itself serves JSON/docs; the SPA is served
# separately (nginx) with its own headers, so this mainly protects /docs & API.
_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-XSS-Protection", "0")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(self), camera=(), microphone=()"
        )
        # Only send docs-friendly CSP for non-docs paths to keep Swagger UI working.
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            response.headers.setdefault("Content-Security-Policy", _CSP)
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies early (defends against memory-exhaustion).

    Most JSON endpoints never need more than MAX_REQUEST_BODY_BYTES (1 MB),
    so that stays the default cap. The itinerary-document upload is a real
    file upload (PDF/DOCX) with its own, larger, documented limit
    (ITINERARY_DOCUMENT_MAX_BYTES) -- without this path-specific override,
    the global 1 MB cap would reject any itinerary file between 1-5 MB
    before it ever reached that endpoint's own size check.
    """

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl is not None:
            limit = settings.MAX_REQUEST_BODY_BYTES
            if request.url.path.endswith("/itinerary-documents"):
                # Multipart adds boundary/header overhead on top of the file
                # itself, so allow a little headroom over the documented cap.
                limit = settings.ITINERARY_DOCUMENT_MAX_BYTES + 50_000
            try:
                if int(cl) > limit:
                    return JSONResponse(
                        status_code=413, content={"detail": "Request body too large"}
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        return await call_next(request)
