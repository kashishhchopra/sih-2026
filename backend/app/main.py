"""FastAPI application entrypoint for MUSAFIR, the Smart Tourist Safety system."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import (
    analytics,
    anchor,
    auth,
    cctv,
    copilot,
    crowd_forecast,
    devices,
    disaster,
    discovery,
    emergency,
    festivals,
    guardian,
    incidents,
    itinerary,
    maps,
    ml,
    permits,
    police_network,
    tourist_id,
    tourists,
    translate,
    trip_planner,
    ws,
    zones,
)
from app.core import scheduler as job_scheduler
from app.core.config import settings
from app.core.joblock import run_locked
from app.core.logging import RequestIDMiddleware, configure_logging
from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.ratelimit import global_rate_limit
from app.db.session import SessionLocal, init_db

configure_logging(json_output=settings.is_production)


def _locked(job_id: str, fn) -> None:
    """Each tick acquires app.models.job_lock.JobLock for `job_id` before
    running, so with WEB_CONCURRENCY > 1 only one worker executes a given
    tick -- the rest see the lock held and skip it silently."""
    run_locked(SessionLocal, job_id, settings.JOB_LOCK_TTL_SECONDS, fn)


def _escalation_tick_job() -> None:
    from app.services.escalation import tick_escalations

    _locked("escalation_tick", tick_escalations)


def _checkin_tick_job() -> None:
    from app.services.checkin import tick_checkins

    _locked("checkin_tick", tick_checkins)


def _retention_purge_tick_job() -> None:
    from app.services.privacy import tick_retention_purge

    _locked("retention_purge_tick", tick_retention_purge)


def _disaster_tick_job() -> None:
    from app.services.disaster import tick_disaster_feed

    _locked("disaster_tick", tick_disaster_feed)


def _anchor_tick_job() -> None:
    from app.services.anchoring import publish_anchor

    _locked("anchor_tick", publish_anchor)


def _token_purge_tick_job() -> None:
    from app.api.auth import purge_expired_revocations

    _locked("token_purge_tick", purge_expired_revocations)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    from app.websocket.manager import manager

    init_db()
    manager.bind_loop(asyncio.get_running_loop())
    if settings.SCHEDULER_ENABLED:
        job_scheduler.start()
        job_scheduler.scheduler.add_job(
            _escalation_tick_job,
            "interval",
            seconds=settings.ESCALATION_TICK_SECONDS,
            id="escalation_tick",
            replace_existing=True,
        )
        job_scheduler.scheduler.add_job(
            _checkin_tick_job,
            "interval",
            seconds=settings.CHECKIN_TICK_SECONDS,
            id="checkin_tick",
            replace_existing=True,
        )
        job_scheduler.scheduler.add_job(
            _retention_purge_tick_job,
            "interval",
            seconds=settings.RETENTION_PURGE_TICK_SECONDS,
            id="retention_purge_tick",
            replace_existing=True,
        )
        job_scheduler.scheduler.add_job(
            _disaster_tick_job,
            "interval",
            seconds=settings.DISASTER_TICK_SECONDS,
            id="disaster_tick",
            replace_existing=True,
        )
        job_scheduler.scheduler.add_job(
            _anchor_tick_job,
            "interval",
            seconds=settings.ANCHOR_TICK_SECONDS,
            id="anchor_tick",
            replace_existing=True,
        )
        job_scheduler.scheduler.add_job(
            _token_purge_tick_job,
            "interval",
            seconds=settings.TOKEN_PURGE_TICK_SECONDS,
            id="token_purge_tick",
            replace_existing=True,
        )
    yield
    if settings.SCHEDULER_ENABLED:
        job_scheduler.shutdown()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.1.0",
    lifespan=lifespan,
    # Hide interactive docs in production by default.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# ---- middleware (order matters: outermost first) ----
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
if settings.allowed_hosts_list and settings.allowed_hosts_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/")
def root():
    return {"name": settings.PROJECT_NAME, "status": "ok",
            "docs": None if settings.is_production else "/docs"}


@app.get("/api/health")
def health():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}


@app.get("/api/config")
def public_config():
    """Non-sensitive config the frontend can consume (map defaults)."""
    return {
        "project_name": settings.PROJECT_NAME,
        "map": {
            "center": [settings.MAP_CENTER_LAT, settings.MAP_CENTER_LNG],
            "zoom": settings.MAP_DEFAULT_ZOOM,
        },
    }


PREFIX = settings.API_V1_PREFIX
# Apply a coarse global per-IP rate limit to all API routers.
_rl = [Depends(global_rate_limit)]
app.include_router(auth.router, prefix=PREFIX, dependencies=_rl)
app.include_router(tourists.router, prefix=PREFIX, dependencies=_rl)
app.include_router(zones.router, prefix=PREFIX, dependencies=_rl)
# emergency.router (a static "/incidents/live" path) must be registered
# BEFORE incidents.router: FastAPI matches routes in registration order, and
# incidents.router's "/incidents/{incident_id}" would otherwise greedily
# claim "/incidents/live" first and fail Pydantic's int coercion on "live"
# rather than ever falling through to this router.
app.include_router(emergency.router, prefix=PREFIX, dependencies=_rl)
app.include_router(incidents.router, prefix=PREFIX, dependencies=_rl)
app.include_router(police_network.router, prefix=PREFIX, dependencies=_rl)
app.include_router(cctv.router, prefix=PREFIX, dependencies=_rl)
app.include_router(tourist_id.router, prefix=PREFIX, dependencies=_rl)
app.include_router(itinerary.router, prefix=PREFIX, dependencies=_rl)
app.include_router(maps.router, prefix=PREFIX, dependencies=_rl)
app.include_router(translate.router, prefix=PREFIX, dependencies=_rl)
app.include_router(analytics.router, prefix=PREFIX, dependencies=_rl)
app.include_router(ml.router, prefix=PREFIX, dependencies=_rl)
app.include_router(devices.router, prefix=PREFIX, dependencies=_rl)
app.include_router(guardian.router, prefix=PREFIX, dependencies=_rl)
app.include_router(copilot.router, prefix=PREFIX, dependencies=_rl)
app.include_router(disaster.router, prefix=PREFIX, dependencies=_rl)
app.include_router(anchor.router, prefix=PREFIX, dependencies=_rl)
app.include_router(trip_planner.router, prefix=PREFIX, dependencies=_rl)
app.include_router(crowd_forecast.router, prefix=PREFIX, dependencies=_rl)
app.include_router(discovery.router, prefix=PREFIX, dependencies=_rl)
app.include_router(festivals.router, prefix=PREFIX, dependencies=_rl)
app.include_router(permits.router, prefix=PREFIX, dependencies=_rl)
app.include_router(ws.router)  # websocket at /ws/alerts (auth via token query param)

# /api/metrics — Prometheus scrape target. Excluded from request logging noise
# and from the app's own docs since it's operational, not part of the domain API.
Instrumentator().instrument(app).expose(app, endpoint="/api/metrics", include_in_schema=False)
