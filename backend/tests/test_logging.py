"""Request-ID middleware: every response carries a correlation id, and a
client-supplied one is honoured rather than overwritten."""
import re


def test_response_carries_a_request_id(client):
    r = client.get("/api/health")
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers["x-request-id"])


def test_client_supplied_request_id_is_propagated(client):
    r = client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["x-request-id"] == "trace-abc-123"


def test_each_request_gets_a_distinct_id_when_not_supplied(client):
    a = client.get("/api/health").headers["x-request-id"]
    b = client.get("/api/health").headers["x-request-id"]
    assert a != b


def test_request_id_survives_an_error_response(client):
    r = client.get("/api/tourists/999999")  # unauthenticated -> 401
    assert "x-request-id" in r.headers


def test_metrics_endpoint_exposed(client):
    r = client.get("/api/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert b"python_gc_objects_collected_total" in r.content


def test_metrics_endpoint_is_not_rate_limited_out_of_scrape_range(client):
    """A Prometheus scraper polls frequently; it must not trip the global
    per-IP rate limiter meant for API clients."""
    for _ in range(20):
        assert client.get("/api/metrics").status_code == 200
