"""Load test for the monitoring pipeline's hottest path: POST /tourists/{id}/location.

This endpoint runs on every GPS ping from every tourist's phone/band, so its
throughput ceiling is the system's real capacity limit -- everything else in
the API is comparatively rare (login once, mark-missing occasionally). It is
also the endpoint the polygon-caching fix in app/services/geo.py targets, so
this file doubles as the way to measure that fix rather than just claim it.

Setup (backend must be running against a seeded database):
    python -m app.scripts.seed
    RATE_LIMIT_ENABLED=false uvicorn app.main:app --port 8000   # separate terminal

The rate limiter is per-IP; every simulated user in a single-host load test
shares one IP, so it would measure the limiter's threshold instead of the
pipeline. In a real deployment, distinct tourist devices have distinct IPs,
so this is a load-test-only relaxation, not a production recommendation.

Run:
    locust -f locustfile.py --host http://127.0.0.1:8000 \\
        --users 100 --spawn-rate 20 --run-time 1m --headless \\
        --csv=locust_report

Then compare p95/p99 for POST /api/tourists/{id}/location before and after a
change (e.g. temporarily reverting geo.clear_polygon_cache-style caching) and
record both numbers -- see the plan's Verification section.

Measured results (this machine, single uvicorn worker, SQLite + WAL,
default DB_POOL_SIZE=20/DB_POOL_MAX_OVERFLOW=20), 25s runs:

    users   p50      p95      p99      failures
    10      83ms     2.5s     2.6s     0
    25      160ms    1.3s     1.5s     0
    40      560ms    2.9s     3.1s     0
    60      1.8s     11s      14s      12 ("database is locked")

Three real bugs surfaced by this exercise and fixed as a result (see git log):
the default SQLAlchemy pool (size 5 + overflow 10) starved under concurrent
SQLite access before any of the above was measurable; ml_service._load() had
an unguarded first-load race across threadpool threads that could trip
CPython's import lock into a deadlock; and SQLite's default busy_timeout=0
meant a second concurrent writer failed immediately instead of queueing.

Ceiling: this configuration serves ~40 concurrent tourists cleanly. Beyond
that, SQLite's single-writer model is the genuine bottleneck -- WAL mode and
a busy_timeout convert outright failures into queueing, but do not remove the
one-writer-at-a-time constraint. This is a demo/dev-scale ceiling, not a
production one: docker-compose.yml already defaults to PostgreSQL, which
does not have this limitation, for exactly this reason.
"""
import random
import threading

import requests
from locust import HttpUser, between, events, task

ADMIN_EMAIL = "admin@tourism.gov.in"
ADMIN_PASSWORD = "admin123"

# Authenticate exactly once for the whole run and share the token/tourist list
# across every simulated user. A fleet of real tourists each log in from their
# own device/IP; piling every simulated user's login onto one shared IP would
# trip the (deliberately strict) login rate limiter and measure the limiter
# instead of the pipeline this test exists to measure.
_shared: dict = {}
_shared_lock = threading.Lock()

# Bounding box roughly matching the seeded Guwahati demo zones, so pings
# actually land inside/near geofences and exercise that code path too.
LAT_RANGE = (26.10, 26.20)
LNG_RANGE = (91.70, 91.78)


class TouristUser(HttpUser):
    """Simulates one tourist's phone sending periodic location pings."""

    wait_time = between(1, 3)

    def on_start(self):
        with _shared_lock:
            if "headers" not in _shared:
                base = self.client.base_url
                r = requests.post(
                    f"{base}/api/auth/login",
                    data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                )
                r.raise_for_status()
                token = r.json()["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                tourists = requests.get(f"{base}/api/tourists", headers=headers).json()
                _shared["headers"] = headers
                _shared["tourist_ids"] = [t["id"] for t in tourists] or [1]
        self.headers = _shared["headers"]
        self.tourist_ids = _shared["tourist_ids"]

    @task
    def send_location_ping(self):
        tid = random.choice(self.tourist_ids)
        lat = random.uniform(*LAT_RANGE)
        lng = random.uniform(*LNG_RANGE)
        speed = random.uniform(2, 15)
        self.client.post(
            f"/api/tourists/{tid}/location",
            json={"lat": lat, "lng": lng, "speed_kmh": speed},
            headers=self.headers,
            name="/api/tourists/[id]/location",
        )

    @task(2)
    def read_safety_score(self):
        tid = random.choice(self.tourist_ids)
        self.client.get(
            f"/api/tourists/{tid}/safety-score",
            headers=self.headers,
            name="/api/tourists/[id]/safety-score",
        )


@events.test_stop.add_listener
def _print_summary(environment, **kwargs):
    stats = environment.stats.get("/api/tourists/[id]/location", "POST")
    if stats and stats.num_requests:
        print(
            f"\nlocation ping: n={stats.num_requests} "
            f"p50={stats.get_response_time_percentile(0.5):.0f}ms "
            f"p95={stats.get_response_time_percentile(0.95):.0f}ms "
            f"p99={stats.get_response_time_percentile(0.99):.0f}ms "
            f"failures={stats.num_failures}"
        )
