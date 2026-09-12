"""CCTV network: real camera feeds for the Police Network Dashboard.

Design, and the reason for each decision:

* **Nothing here invents a camera or a stream URL.** A camera row reaches
  this service one of two ways -- an operator registered it (POST
  /police-network/cameras, the way a real force onboards its own cameras),
  or a configured external provider supplied it (`import_from_provider`,
  off by default). With neither, `list_cameras` returns an empty list and
  the dashboard says there are no feeds. That is a correct outcome, not a
  cue to fabricate one.

* **LIVE is probed, never asserted.** `Camera.status` is the operator's
  enable/disable flag and `Camera.stream_status` is only a cache; the state
  the API reports comes from actually reaching the stream (`probe_stream`)
  and is re-checked once the cache goes stale. A row existing in the
  database can never, on its own, make a camera read LIVE.

* **Credentials stay server-side.** A stream URL's userinfo (rtsp://user:pass@)
  is stripped before the record is ever serialised toward a browser, and
  RTSP is reported as not directly playable rather than handed to the
  frontend to figure out.

Same shape as this project's other external adapters (services/weather.py,
services/maps.py, services/disaster.py): real when configured, honest and
empty when not, and the payload always says which.
"""
from __future__ import annotations

import concurrent.futures
import logging
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import utc_now
from app.models.police import Camera, PoliceStation

logger = logging.getLogger(__name__)

# What the frontend's player knows how to render. "none" means this camera is
# a coverage record with no viewable feed -- a normal, supported state.
# "jpeg" is a still-image camera that must be re-fetched to stay current;
# "mjpeg" is a continuous multipart stream. They are separate types because
# the player has to treat them differently -- rendering a still once and
# calling it LIVE would show a frozen frame.
STREAM_TYPES = ("hls", "mjpeg", "jpeg", "webrtc", "mp4", "rtsp", "none")

# Connection states reported to the dashboard.
LIVE = "live"
OFFLINE = "offline"
NO_STREAM = "no_stream"        # camera exists, no feed URL configured
DISABLED = "disabled"          # operator turned this camera off
UNPLAYABLE = "unplayable"      # real stream, but not viewable in a browser (RTSP)
UNAVAILABLE = "unavailable"    # source answers, but is publishing a "camera
                               # unavailable"/"down for construction" notice
                               # image instead of a view -- not a live picture
UNKNOWN = "unknown"            # not probed yet / probing suppressed


def strip_credentials(url: str | None) -> str | None:
    """Remove any user:password@ from a stream URL before it leaves the
    backend. A private RTSP credential must never reach frontend code."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.netloc or "@" not in parts.netloc:
        return url
    host = parts.netloc.rsplit("@", 1)[1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def infer_stream_type(url: str | None) -> str:
    """Best-effort stream type from the URL itself, used only when a source
    didn't state one explicitly."""
    if not url:
        return "none"
    lowered = url.lower().split("?", 1)[0]
    if lowered.startswith("rtsp://"):
        return "rtsp"
    if lowered.endswith(".m3u8"):
        return "hls"
    if lowered.endswith((".mp4", ".webm")):
        return "mp4"
    if lowered.endswith((".mjpg", ".mjpeg", ".cgi")) or "mjpeg" in lowered:
        return "mjpeg"
    return "none"


def _looks_like_notice_card(payload: bytes) -> bool:
    """Whether an image is an operator notice card rather than a camera view.

    Road-camera networks keep publishing a JPEG when a camera is down -- a
    flat white card reading "Temporarily Unavailable" or "Down for
    Construction". It is a valid 200 response, so reachability alone calls
    it LIVE and the console ends up showing a caption where a road should
    be, which is precisely the fake-LIVE this feature exists to avoid.

    The giveaway is that these cards are synthetic: most of the frame is one
    exact shade. A real photograph -- even a snowy whiteout, which is the
    obvious false positive to worry about -- carries sensor noise and
    gradients, so no single luminance value dominates it. Measured on this
    project's own feeds: notice cards ~79% of pixels in one bucket, real
    frames 2-5%.
    """
    try:
        import io

        from PIL import Image
    except ImportError:  # Pillow absent: skip the check rather than guess
        return False
    try:
        image = Image.open(io.BytesIO(payload)).convert("L")
        histogram = image.histogram()
        total = sum(histogram)
        if not total:
            return False
        return (max(histogram) / total) >= settings.CCTV_IMAGE_FLAT_RATIO
    except Exception as e:  # unreadable image -> let reachability decide
        logger.info("CCTV image inspection failed: %s", e)
        return False


def probe_stream(url: str, stream_type: str) -> str:
    """Actually reach for the stream and report what came back.

    Returns LIVE / OFFLINE / UNPLAYABLE. Never raises: an unreachable camera
    is an expected, routine condition on a surveillance network, not an
    error the dashboard should blow up on.
    """
    if stream_type == "rtsp":
        # Real stream, but no browser plays RTSP directly -- it needs a
        # server-side transcode this deployment doesn't run. Saying so is
        # honest; claiming LIVE and rendering nothing would not be.
        return UNPLAYABLE
    if settings.is_test:
        # Hermetic tests: no outbound network. Tests that want a specific
        # result monkeypatch this function.
        return UNKNOWN
    try:
        timeout = settings.CCTV_PROBE_TIMEOUT_SECONDS
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            if stream_type == "hls":
                resp = client.get(url, headers={"Range": "bytes=0-2047"})
                resp.raise_for_status()
                # A real HLS playlist starts with the #EXTM3U tag. Anything
                # else (a login page, an error page) is not a live feed.
                return LIVE if "#EXTM3U" in resp.text[:2048] else OFFLINE
            if stream_type == "jpeg":
                # A still frame is small, so fetch it whole and look at what
                # the camera is actually publishing -- not just whether the
                # request succeeded. (Only safe for "jpeg": a true multipart
                # MJPEG response never ends.)
                resp = client.get(url)
                if resp.status_code >= 400:
                    return OFFLINE
                return UNAVAILABLE if _looks_like_notice_card(resp.content) else LIVE
            # MJPEG/MP4/WebRTC signalling: a reachable endpoint returning a
            # success status is as much as can be checked without decoding.
            resp = client.head(url)
            if resp.status_code >= 400:
                # Not every camera implements HEAD; retry as a ranged GET
                # before calling it offline.
                resp = client.get(url, headers={"Range": "bytes=0-1023"})
            return LIVE if resp.status_code < 400 else OFFLINE
    except (httpx.HTTPError, ValueError) as e:
        logger.info("CCTV probe failed for %s: %s", url, e)
        return OFFLINE


def camera_status(db: Session, cam: Camera, force: bool = False) -> str:
    """Current connection state for one camera, re-probing when the cached
    result has gone stale. Commits the cache so concurrent dashboard clients
    share one probe rather than each hammering the camera."""
    if (cam.status or "").lower() != "active":
        return DISABLED
    if not cam.stream_url:
        return NO_STREAM

    fresh_for = timedelta(seconds=settings.CCTV_STATUS_CACHE_SECONDS)
    checked = cam.stream_checked_at
    if not force and cam.stream_status and checked is not None:
        if _as_naive_utc(utc_now()) - _as_naive_utc(checked) < fresh_for:
            return cam.stream_status

    state = probe_stream(cam.stream_url, cam.stream_type or infer_stream_type(cam.stream_url))
    cam.stream_status = state
    cam.stream_checked_at = utc_now()
    db.commit()
    return state


def _as_naive_utc(dt: datetime) -> datetime:
    """Stored timestamps are naive UTC; utc_now() may be aware depending on
    configuration. Compare them on the same footing."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def resolve_station_id(db: Session, cam: Camera) -> int | None:
    """Which station is responsible for this camera.

    An explicit `assigned_station_id` wins; otherwise it falls out of the
    existing Zone -> PoliceStation relationship (a station covers exactly one
    zone -- see models/police.py), so the CCTV layer plugs into the
    Safety Zone -> Police Station -> SOS chain instead of duplicating it.
    """
    if cam.assigned_station_id is not None:
        return cam.assigned_station_id
    if cam.zone_id is None:
        return None
    station = (
        db.query(PoliceStation).filter(PoliceStation.zone_id == cam.zone_id).first()
    )
    return station.id if station else None


def serialize(db: Session, cam: Camera, *, connection: str | None = None) -> dict:
    """One camera as the dashboard sees it -- credentials stripped, station
    resolved, connection state included."""
    stream_type = cam.stream_type or infer_stream_type(cam.stream_url)
    return {
        "id": cam.id,
        "label": cam.label,
        "zone_id": cam.zone_id,
        "lat": cam.lat,
        "lng": cam.lng,
        "status": cam.status,
        "installed_at": cam.installed_at,
        "stream_url": strip_credentials(cam.stream_url),
        "stream_type": stream_type,
        "feed_source": cam.feed_source or "manual",
        "source_url": cam.source_url,
        "attribution": cam.attribution,
        "assigned_station_id": resolve_station_id(db, cam),
        "connection": connection if connection is not None else camera_status(db, cam),
        "last_checked_at": cam.stream_checked_at,
    }


def _needs_probe(cam: Camera) -> bool:
    """Whether this camera's cached status is missing or too old to reuse."""
    if (cam.status or "").lower() != "active" or not cam.stream_url:
        return False
    if not cam.stream_status or cam.stream_checked_at is None:
        return True
    age = _as_naive_utc(utc_now()) - _as_naive_utc(cam.stream_checked_at)
    return age >= timedelta(seconds=settings.CCTV_STATUS_CACHE_SECONDS)


def refresh_statuses(db: Session, cams: list[Camera]) -> None:
    """Re-probe several cameras at once, bounded by a wall-clock deadline.

    Probing sequentially inside the request made the dashboard wait on the
    slowest camera in the network -- with a handful of cameras and a
    multi-second timeout each, the console sat on "Loading CCTV Network…"
    for ~16s. Cameras are independent, so probe them in parallel and stop
    waiting at the deadline: anything unfinished simply keeps its previous
    cached state and gets picked up by the next poll, which is exactly what
    the dashboard's periodic refresh is for.

    The probe itself is pure network I/O and never touches the session, so
    it is safe off-thread; results are written back here on the caller's
    thread.
    """
    stale = [c for c in cams if _needs_probe(c)]
    if not stale:
        return
    deadline = settings.CCTV_LIST_PROBE_DEADLINE_SECONDS
    results: dict[int, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(probe_stream, c.stream_url,
                        c.stream_type or infer_stream_type(c.stream_url)): c.id
            for c in stale
        }
        done, pending = concurrent.futures.wait(futures, timeout=deadline)
        for fut in done:
            try:
                results[futures[fut]] = fut.result()
            except Exception as e:  # a probe must never break the listing
                logger.info("CCTV probe raised: %s", e)
        for fut in pending:
            fut.cancel()
    if not results:
        return
    now = utc_now()
    for cam in stale:
        if cam.id in results:
            cam.stream_status = results[cam.id]
            cam.stream_checked_at = now
    db.commit()


def list_cameras(
    db: Session,
    *,
    q: str | None = None,
    station_id: int | None = None,
    zone_id: int | None = None,
    connection: str | None = None,
    probe: bool = True,
) -> list[dict]:
    """Every registered camera, filtered server-side.

    Filtering lives here rather than in the browser so a force with hundreds
    of cameras doesn't ship the whole directory to every dashboard.

    Cameras that actually carry a feed are listed first: a surveillance
    console is for watching cameras, so coverage-only records shouldn't
    push the live ones below the fold.
    """
    cams = db.query(Camera).order_by(Camera.id).all()
    if probe:
        refresh_statuses(db, cams)
    out: list[dict] = []
    for cam in cams:
        state = _cached_state(cam)
        record = serialize(db, cam, connection=state)
        if q:
            needle = q.strip().lower()
            haystack = " ".join(
                str(v) for v in (record["label"], record["feed_source"], cam.id) if v
            ).lower()
            if needle not in haystack:
                continue
        if station_id is not None and record["assigned_station_id"] != station_id:
            continue
        if zone_id is not None and record["zone_id"] != zone_id:
            continue
        if connection is not None and record["connection"] != connection:
            continue
        out.append(record)
    order = {LIVE: 0, UNKNOWN: 1, UNAVAILABLE: 2, OFFLINE: 3, UNPLAYABLE: 4,
             NO_STREAM: 5, DISABLED: 6}
    out.sort(key=lambda r: (order.get(r["connection"], 9), r["id"]))
    return out


def _cached_state(cam: Camera) -> str:
    """This camera's state from what is already stored -- no network I/O.

    Used by the listing, which refreshes stale entries up-front (and in
    parallel) rather than probing camera-by-camera while serialising.
    """
    if (cam.status or "").lower() != "active":
        return DISABLED
    if not cam.stream_url:
        return NO_STREAM
    return cam.stream_status or UNKNOWN


def network_summary(db: Session, cameras: list[dict]) -> dict:
    """Counts the console header shows, plus whether an external provider is
    configured at all -- so the UI can distinguish "no cameras registered"
    from "provider misconfigured"."""
    return {
        "total": len(cameras),
        "live": sum(1 for c in cameras if c["connection"] == LIVE),
        "offline": sum(1 for c in cameras if c["connection"] == OFFLINE),
        "no_stream": sum(1 for c in cameras if c["connection"] == NO_STREAM),
        "unavailable": sum(1 for c in cameras if c["connection"] == UNAVAILABLE),
        "provider": settings.CCTV_PROVIDER or None,
        "provider_configured": bool(settings.CCTV_PROVIDER and settings.CCTV_PROVIDER_URL),
        "refresh_interval_seconds": settings.CCTV_REFRESH_INTERVAL_SECONDS,
    }


# ---------------- external provider import ----------------

def _provider_records() -> list[dict] | None:
    """Fetch raw camera records from the configured provider.

    Returns None when no provider is configured or the fetch fails -- the
    caller then leaves the database exactly as it was rather than clearing
    or inventing cameras.

    "json" expects the feed to return a list of objects (or {"cameras": [...]})
    carrying at least a name/label, a latitude, a longitude and a stream URL.
    Deliberately generic: this project has no contracted CCTV vendor, and
    guessing one vendor's proprietary schema would be inventing an
    integration that has never been run against the real thing.
    """
    if settings.CCTV_PROVIDER != "json" or not settings.CCTV_PROVIDER_URL:
        return None
    if settings.is_test:
        return None
    headers = {}
    if settings.CCTV_API_KEY:
        headers["Authorization"] = f"Bearer {settings.CCTV_API_KEY}"
    try:
        with httpx.Client(timeout=settings.CCTV_PROBE_TIMEOUT_SECONDS) as client:
            resp = client.get(settings.CCTV_PROVIDER_URL, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("CCTV provider fetch failed: %s", e)
        return None
    return _flatten_records(payload)


def _flatten_records(payload) -> list[dict] | None:
    """Pull camera objects out of whatever shape the feed uses.

    Open datasets nest cameras under region/county keys rather than
    returning one flat list, so walk the structure and take every object
    that looks like a camera (has a URL and a latitude) instead of assuming
    a single documented layout.
    """
    if isinstance(payload, list) and all(isinstance(i, dict) for i in payload):
        if any("url" in i or "streamUrl" in i or "stream_url" in i for i in payload):
            return payload
    found: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            has_url = any(k in node for k in ("url", "streamUrl", "stream_url"))
            has_pos = any(k in node for k in ("latitude", "lat"))
            if has_url and has_pos:
                found.append(node)
                return
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found or None


def _is_importable_stream(url: str | None) -> bool:
    """Whether a provider-supplied URL is safe and useful to store.

    Open camera datasets are crowdsourced and do leak operator RTSP
    credentials and internal LAN addresses (real example seen in the wild:
    `rtsp://admin:...@10.53.56.67:554/`). Those are somebody's private
    camera, not a public feed: refuse them at the import boundary rather
    than storing a credential we would then have to remember to strip.
    """
    if not url:
        return True  # a coverage-only record is fine
    lowered = url.lower()
    if lowered.startswith("rtsp://"):
        return False
    if "@" in urlsplit(url).netloc:  # embedded userinfo/credentials
        return False
    host = urlsplit(url).hostname or ""
    if host in ("localhost", "127.0.0.1") or host.startswith(
            ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
             "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
             "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.")):
        return False
    return True


def _coerce(record: dict) -> dict | None:
    """Map one provider record onto our columns, or None if it lacks the
    minimum a camera needs to be placed on a map (or isn't safe to store).

    Key names are matched loosely because open camera datasets don't share
    one schema -- `description` is the camera's name in some, `name` or
    `title` in others.
    """
    label = (record.get("name") or record.get("label") or record.get("title")
             or record.get("description"))
    lat = record.get("latitude", record.get("lat"))
    lng = record.get("longitude", record.get("lng", record.get("lon")))
    url = record.get("streamUrl") or record.get("stream_url") or record.get("url")
    if not label or lat is None or lng is None:
        return None
    if not _is_importable_stream(url):
        return None
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    # Some datasets state the delivery format themselves ("M3U8",
    # "IMAGE_STREAM"); otherwise fall back to inferring it from the URL.
    declared = (record.get("streamType") or record.get("stream_type")
                or record.get("format") or "").strip().lower()
    stream_type = {"m3u8": "hls", "image_stream": "jpeg"}.get(declared, declared)
    if stream_type not in STREAM_TYPES:
        stream_type = infer_stream_type(url)
    return {
        "label": str(label)[:200],
        "lat": lat,
        "lng": lng,
        "stream_url": url or None,
        "stream_type": stream_type if stream_type in STREAM_TYPES else "none",
        # Credit the host actually serving the feed when the record itself
        # doesn't name a source -- "json" (the adapter's name) tells an
        # operator nothing about where the picture came from.
        "feed_source": (record.get("source") or record.get("provider")
                        or (urlsplit(url).hostname if url else None)
                        or settings.CCTV_PROVIDER or "provider"),
        "source_url": record.get("sourceUrl") or record.get("source_url"),
        "attribution": record.get("attribution") or record.get("license"),
    }


def import_from_provider(db: Session) -> dict:
    """Refresh the camera directory from the configured provider.

    Upserts on (label, lat, lng) so re-running doesn't duplicate rows, and
    never deletes operator-registered cameras.
    """
    records = _provider_records()
    if records is None:
        return {
            "configured": bool(settings.CCTV_PROVIDER and settings.CCTV_PROVIDER_URL),
            "imported": 0,
            "updated": 0,
            "detail": "No CCTV provider configured or provider unreachable.",
        }
    imported = updated = 0
    skipped_dead = 0
    probes = 0
    limit = settings.CCTV_PROVIDER_MAX_CAMERAS
    bbox = _parse_bbox(settings.CCTV_PROVIDER_BBOX)
    for raw in records:
        if limit and (imported + updated) >= limit:
            break
        if not isinstance(raw, dict):
            continue
        fields = _coerce(raw)
        if fields is None:
            continue
        # Only take cameras in this deployment's area of responsibility.
        if bbox and not _within(bbox, fields["lat"], fields["lng"]):
            continue
        # Validate the source before storing it: an open feed lists plenty
        # of cameras that no longer answer, and importing those would fill
        # the console with rows that can only ever read OFFLINE.
        if (settings.CCTV_PROVIDER_VALIDATE and fields["stream_url"]
                and fields["stream_type"] in ("hls", "jpeg", "mjpeg")):
            if probes >= settings.CCTV_PROVIDER_PROBE_BUDGET:
                break
            probes += 1
            # Skip only on a definitive failure: an inconclusive probe
            # (UNKNOWN) must not silently drop a camera that may be fine.
            if probe_stream(fields["stream_url"], fields["stream_type"]) in (
                    OFFLINE, UNAVAILABLE):
                skipped_dead += 1
                continue
        existing = (
            db.query(Camera)
            .filter(Camera.label == fields["label"],
                    Camera.lat == fields["lat"], Camera.lng == fields["lng"])
            .first()
        )
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
            existing.stream_status = None  # force a fresh probe
            existing.stream_checked_at = None
            updated += 1
        else:
            db.add(Camera(**fields))
            imported += 1
    db.commit()
    detail = f"{imported} added, {updated} updated."
    if skipped_dead:
        detail += f" {skipped_dead} skipped (source not reachable)."
    return {"configured": True, "imported": imported, "updated": updated,
            "detail": detail}


def _parse_bbox(raw: str) -> tuple[float, float, float, float] | None:
    """"minLat,minLng,maxLat,maxLng" -> tuple, or None if unset/malformed."""
    if not raw:
        return None
    try:
        min_lat, min_lng, max_lat, max_lng = (float(p) for p in raw.split(","))
    except (TypeError, ValueError):
        logger.warning("Ignoring malformed CCTV_PROVIDER_BBOX: %r", raw)
        return None
    return (min_lat, min_lng, max_lat, max_lng)


def _within(bbox: tuple[float, float, float, float], lat: float, lng: float) -> bool:
    min_lat, min_lng, max_lat, max_lng = bbox
    return min_lat <= lat <= max_lat and min_lng <= lng <= max_lng
