"""Application configuration — fully environment-driven, safe defaults for dev.

Nothing security-sensitive is hardcoded. In production (ENVIRONMENT=production)
the app refuses to start unless a strong SECRET_KEY is provided.
"""
from __future__ import annotations

import secrets
import warnings
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ---- environment ----
    ENVIRONMENT: str = "development"  # development | production
    PROJECT_NAME: str = "MUSAFIR — Smart Tourist Safety Monitoring & Incident Response System"
    API_V1_PREFIX: str = "/api"

    # ---- database ----
    # SQLite for dev; set DATABASE_URL=postgresql+psycopg://user:pass@host/db in prod
    DATABASE_URL: str = "sqlite:///./tourist_safety.db"
    DB_POOL_SIZE: int = 20
    DB_POOL_MAX_OVERFLOW: int = 20

    # ---- auth / JWT ----
    # Leave empty to auto-generate an ephemeral key in dev (tokens reset on restart).
    SECRET_KEY: str = ""
    # Where a generated dev key is cached so it survives restarts (dev only).
    DEV_SECRET_FILE: str = ".dev_secret"
    ALGORITHM: str = "HS256"
    # Short-lived on purpose: the refresh token (below) is what's actually
    # revocable, so access tokens should expire quickly rather than need
    # per-request denylist checks.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # ---- refresh-token cookie ----
    # The refresh token is set as an httpOnly cookie so it's never readable
    # by JS (unlike the access token, which the frontend keeps in memory) --
    # closes the XSS-exfiltration path on the one token that's actually
    # long-lived. Secure should be True behind HTTPS (i.e. always in prod);
    # False here only so plain-HTTP local dev still works.
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_PATH: str = "/api/auth"
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_SAMESITE: str = "strict"

    # ---- password policy ----
    MIN_PASSWORD_LENGTH: int = 8

    # ---- rate limiting (per client IP) ----
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: int = 10          # attempts
    LOGIN_RATE_WINDOW_SECONDS: int = 300
    GLOBAL_RATE_LIMIT: int = 240        # requests
    GLOBAL_RATE_WINDOW_SECONDS: int = 60
    REGISTRATION_RATE_LIMIT: int = 5    # public digital-ID registrations
    REGISTRATION_RATE_WINDOW_SECONDS: int = 3600

    # ---- request hardening ----
    MAX_REQUEST_BODY_BYTES: int = 1_000_000  # 1 MB

    # ---- ML ----
    ML_MODELS_DIR: str = "ml_models"

    # ---- notifications ----
    # "console" logs instead of sending (default -- no external service
    # needed). See app/services/notifications.py for the extension point.
    NOTIFICATION_CHANNEL: str = "console"
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # ---- Fair Price: local transport fare rate card (services/fare.py) ----
    # Base fare (INR) + per-km + per-minute rate for each transport type.
    # Defaults are broadly representative starting rates, NOT any specific
    # city's official tariff -- override with the real RTO/state-published
    # tariff for your deployment's city so estimates are locally accurate.
    FARE_AUTO_BASE: float = 30.0
    FARE_AUTO_PER_KM: float = 15.0
    FARE_AUTO_PER_MIN: float = 1.0
    FARE_TAXI_BASE: float = 50.0
    FARE_TAXI_PER_KM: float = 20.0
    FARE_TAXI_PER_MIN: float = 1.5
    FARE_CAB_BASE: float = 60.0
    FARE_CAB_PER_KM: float = 18.0
    FARE_CAB_PER_MIN: float = 1.5
    FARE_BIKE_BASE: float = 20.0
    FARE_BIKE_PER_KM: float = 8.0
    FARE_BIKE_PER_MIN: float = 0.5

    # ---- public holidays (Calendarific -- free tier, key required) ----
    # Used by Crowd & Queue Forecast and Festival & Local Event Intelligence
    # for a real holiday-travel-window signal instead of a hand-maintained
    # date table. Empty = that signal is simply absent (never a fabricated
    # holiday) -- get a free key at https://calendarific.com/signup.
    # ISO 3166-1 alpha-2; India by default.
    CALENDARIFIC_API_KEY: str = ""
    HOLIDAYS_COUNTRY_CODE: str = "IN"
    HOLIDAYS_API_TIMEOUT_SECONDS: float = 4.0
    HOLIDAYS_CACHE_TTL_SECONDS: int = 86_400  # a year's holiday list is static; refresh daily

    # ---- Discovery: live OpenStreetMap Overpass lookups ----
    # Real hidden-gem/regional-food/homestay places near the tourist, fetched
    # live from the free public Overpass API (no key). Off by default at
    # request time is NOT the default here -- see services/discovery.py's
    # module docstring for why a short timeout + cache keep this safe to call
    # synchronously (falls back to the seeded/cached DB rows on any failure).
    DISCOVERY_LIVE_ENABLED: bool = True
    OVERPASS_API_URL: str = "https://overpass-api.de/api/interpreter"
    # The public instance is shared/rate-limited and can be slow; a request
    # here blocks the Discovery API call, so this is a real timeout, not
    # a knob to raise indefinitely -- a slow response falls back to the
    # database rather than making the tourist wait.
    OVERPASS_TIMEOUT_SECONDS: float = 8.0
    DISCOVERY_CACHE_TTL_SECONDS: int = 3600

    # ---- weather (safety-score input) ----
    # Empty = use the deterministic mock (no network needed, works offline).
    # Set to a real OpenWeatherMap API key (free tier) to use live conditions.
    OPENWEATHER_API_KEY: str = ""
    OPENWEATHER_TIMEOUT_SECONDS: float = 3.0
    WEATHER_CACHE_TTL_SECONDS: int = 600

    # ---- dispatch / escalation ----
    # Assumed average travel speed for a responding unit, used only to turn a
    # distance into a rough ETA estimate for the dispatch-ranking UI -- not a
    # claim about real traffic conditions.
    DISPATCH_ASSUMED_SPEED_KMH: float = 30.0
    # How often the background escalation job re-checks open incidents.
    ESCALATION_TICK_SECONDS: int = 30
    # How long an incident sits at each escalation stage before auto-advancing
    # to the next one if nobody has acknowledged it.
    ESCALATION_STAGE_TIMEOUT_SECONDS: int = 120

    # ---- SOS live location sharing (see services/emergency_location.py) ----
    # A ping older than this is still "recent enough" to call LIVE; older
    # than OFFLINE and the police dashboard must not claim it's live at all.
    EMERGENCY_LOCATION_LIVE_SECONDS: int = 15
    EMERGENCY_LOCATION_STALE_SECONDS: int = 45
    # Bounded movement trail per incident -- "recent path", not a permanent
    # location history. Enforced by trimming older pings on every insert.
    EMERGENCY_LOCATION_TRAIL_MAX_POINTS: int = 60
    # A implied speed above this between two consecutive pings is physically
    # implausible (teleportation/spoofing) -- flagged, never auto-escalated.
    EMERGENCY_LOCATION_MAX_PLAUSIBLE_KMH: float = 250.0

    # ---- check-in / check-out ----
    # How often the background job re-checks planned check-ins.
    CHECKIN_TICK_SECONDS: int = 30
    # Grace period after a missed check-in deadline before it escalates from
    # an alert to an incident -- "well before an SOS is ever pressed."
    CHECKIN_GRACE_MINUTES: int = 30

    # ---- privacy & consent ----
    # How often the background job purges location history past its
    # retention window (see services/privacy.py).
    RETENTION_PURGE_TICK_SECONDS: int = 3600
    # How often expired revoked-token rows are purged (see api/auth.py).
    TOKEN_PURGE_TICK_SECONDS: int = 3600

    # ---- scheduler / cross-worker job locking ----
    # False disables the scheduler entirely (e.g. a worker that should never
    # run background ticks). True is the default for a single-worker deploy;
    # with WEB_CONCURRENCY > 1 the job lock (app/core/joblock.py) still
    # prevents duplicate execution even though every worker has this True.
    SCHEDULER_ENABLED: bool = True
    JOB_LOCK_TTL_SECONDS: int = 120

    # ---- disaster & weather alert feeds ----
    # How often the background job refreshes area-level hazard advisories.
    DISASTER_TICK_SECONDS: int = 120
    # Name of a real disaster-advisory provider, if one is ever wired up.
    # Empty (the default) means the deterministic simulator runs -- no
    # external API/key is assumed to exist for this project. See
    # services/disaster.py.
    DISASTER_FEED_PROVIDER: str = ""
    # A CAP 1.2 feed URL to poll when DISASTER_FEED_PROVIDER is set. No
    # default is assumed live/stable -- NDMA SACHET's public feed is served
    # by a JS SPA with no documented XML/JSON endpoint discoverable without
    # provider cooperation (see services/cap.py's module docstring). Point
    # this at whatever CAP 1.2 source is actually available to you.
    DISASTER_FEED_URL: str = ""

    # ---- CCTV network (services/cctv.py) ----
    # Where camera records come from. "" (default) means the database is the
    # only source: an operator registers each camera and its real stream URL
    # through POST /police-network/cameras, exactly as a real police network
    # would. Setting a provider lets POST /cctv/refresh additionally import
    # camera metadata from an external open-data/public-camera API.
    #
    # Nothing here is populated with invented cameras or invented stream
    # URLs: with no provider configured and nothing registered, /cctv simply
    # returns an empty list and the dashboard says so.
    CCTV_PROVIDER: str = ""            # "" (db only) | "json"
    CCTV_PROVIDER_URL: str = ""        # feed URL when CCTV_PROVIDER is set
    CCTV_API_KEY: str = ""             # sent as the provider's API key when required
    # Upper bound on one import, so pointing at a national feed of tens of
    # thousands of cameras can't flood the directory (or the probe budget).
    CCTV_PROVIDER_MAX_CAMERAS: int = 40
    # Only import cameras inside this area of responsibility, as
    # "minLat,minLng,maxLat,maxLng". Empty = import from anywhere in the
    # feed. A national feed covers far more ground than one force polices.
    CCTV_PROVIDER_BBOX: str = ""
    # Probe each candidate during import and store only the ones that
    # actually answer, so the directory doesn't fill with dead URLs the feed
    # still lists. Bounded by CCTV_PROVIDER_PROBE_BUDGET.
    CCTV_PROVIDER_VALIDATE: bool = True
    CCTV_PROVIDER_PROBE_BUDGET: int = 120
    # A camera's LIVE/OFFLINE state is probed against its real stream, never
    # read off the stored row. These bound that probe and how long its result
    # is reused before re-probing.
    CCTV_PROBE_TIMEOUT_SECONDS: float = 4.0
    CCTV_STATUS_CACHE_SECONDS: int = 30
    # Hard ceiling on how long the camera listing will wait for stale
    # statuses to re-probe. Anything slower keeps its previous state and is
    # picked up by the next poll -- the dashboard must never hang on the
    # slowest camera in the network.
    CCTV_LIST_PROBE_DEADLINE_SECONDS: float = 3.0
    # A still-image camera whose frame is this dominated by a single shade is
    # an operator "camera unavailable" notice card, not a view. Measured on
    # real feeds: notice cards ~0.79, actual camera frames 0.02-0.05.
    CCTV_IMAGE_FLAT_RATIO: float = 0.5
    # How often the dashboard re-polls camera status (seconds), served to the
    # frontend so the interval is configured in one place.
    CCTV_REFRESH_INTERVAL_SECONDS: int = 30

    # ---- external services: maps / translation / speech ----
    # All blank by default -- every feature that would use these has a
    # deterministic demo/mock fallback (see services/maps.py,
    # services/translation.py) so the app runs fully offline with no keys.
    # A response built from the fallback is always marked demo/mock in its
    # payload so the frontend can say so, not silently pass mock data off
    # as live.
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_TRANSLATE_API_KEY: str = ""
    SPEECH_TO_TEXT_API_KEY: str = ""
    TEXT_TO_SPEECH_API_KEY: str = ""
    # Itinerary document upload: max file size accepted for extraction.
    ITINERARY_DOCUMENT_MAX_BYTES: int = 5_000_000  # 5 MB

    # ---- open-ended assistant (see services/llm.py) ----
    # The intent router answers safety-critical questions from real DB rows;
    # this backs everything else, so the assistant isn't limited to a fixed
    # command list. Default "auto": a cloud key if one is configured, else a
    # local Ollama model (free, no key, nothing leaves the machine), else
    # nothing -- in which case the assistant simply says what it can do.
    LLM_ENABLED: bool = True
    LLM_PROVIDER: str = "auto"  # auto | ollama | openai | anthropic | none
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_TOKENS: int = 250  # answers are read aloud -- keep them short
    LLM_TEMPERATURE: float = 0.3
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"

    # ---- live-feed fallback ladder (see services/feeds.py) ----
    # False = snapshot-only, no network calls at all -- the demo-venue kill
    # switch (e.g. a hackathon hall with no reliable internet).
    FEEDS_ENABLED: bool = True
    FEED_CACHE_DIR: str = "feed_cache"
    FEED_TIMEOUT_SECONDS: int = 600

    # ---- external hash-chain anchoring ----
    # How often the background job anchors the chain's current root hash.
    ANCHOR_TICK_SECONDS: int = 1800
    # Where anchors are published. "local" (the default) appends to a local,
    # append-only JSON ledger file standing in for an external timestamping
    # service -- see services/anchoring.py for why, and how to point this at
    # a real one.
    ANCHOR_TARGET: str = "local"
    # Where the "external" ledger file lives -- stands in for a real public
    # timestamping service. A real deployment would point this integration
    # at an actual external store instead; see services/anchoring.py.
    ANCHOR_LEDGER_PATH: str = "anchor_ledger.jsonl"

    # ---- domain thresholds ----
    ROUTE_DEVIATION_THRESHOLD_M: float = 2000.0
    ANOMALY_INCIDENT_DEDUPE_MINUTES: int = 5
    # Digital Tourist Safety ID: a trip within this many hours of its end
    # shows as "expiring_soon" rather than "active" -- see services/tourist_id.py.
    ID_EXPIRING_SOON_HOURS: float = 24.0
    # How far ahead (minutes) each ping's trajectory is projected to check for
    # an imminent high-risk/restricted zone crossing.
    TRAJECTORY_HORIZON_MIN: float = 15.0
    # Lateral offset (metres) applied to a candidate route's midpoint waypoint
    # when perturbing the direct origin->destination line (see routing.py).
    ROUTE_CANDIDATE_OFFSET_M: float = 250.0
    # Distance (metres) between risk-sampling points along a candidate route.
    ROUTE_SAMPLE_INTERVAL_M: float = 100.0

    # ---- map defaults (surfaced to the frontend via /api/config) ----
    MAP_CENTER_LAT: float = 26.1445
    MAP_CENTER_LNG: float = 91.7362
    MAP_DEFAULT_ZOOM: int = 13

    # ---- CORS / hosts (comma-separated in env) ----
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    ALLOWED_HOSTS: str = "*"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT.lower() == "test"

    @field_validator("ENVIRONMENT")
    @classmethod
    def _valid_env(cls, v: str) -> str:
        if v.lower() not in ("development", "production", "test"):
            raise ValueError("ENVIRONMENT must be development, production or test")
        return v.lower()

    @model_validator(mode="after")
    def _finalize_secret(self) -> Settings:
        if not self.SECRET_KEY:
            if self.is_production:
                raise RuntimeError(
                    "SECRET_KEY must be set in production. Generate one with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
            # Dev convenience: generate a key once and persist it to a
            # gitignored file. It must be STABLE across restarts because the
            # digital-ID hash chain is keyed with it (see services/hashchain.py)
            # -- a fresh key each boot would invalidate every existing chain.
            key_file = Path(self.DEV_SECRET_FILE)
            if key_file.exists():
                self.SECRET_KEY = key_file.read_text(encoding="utf-8").strip()
            else:
                self.SECRET_KEY = secrets.token_urlsafe(48)
                try:
                    key_file.write_text(self.SECRET_KEY, encoding="utf-8")
                except OSError:
                    warnings.warn(
                        "Could not persist the dev SECRET_KEY; hash chains and "
                        "tokens will reset on restart.",
                        stacklevel=2,
                    )
        elif len(self.SECRET_KEY) < 32 and self.is_production:
            raise RuntimeError("SECRET_KEY is too short for production (need >= 32 chars).")

        if self.is_production and "*" in self.allowed_hosts_list:
            warnings.warn("ALLOWED_HOSTS='*' in production is insecure — set explicit hosts.",
                          stacklevel=2)
        return self


settings = Settings()
