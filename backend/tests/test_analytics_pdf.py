"""Analytics PDF Export (GET /analytics/pdf)."""
from tests.conftest import make_tourist


def test_analytics_pdf_returns_pdf_bytes(client, admin_headers, db):
    make_tourist(db)
    r = client.get("/api/analytics/pdf", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_analytics_pdf_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/analytics/pdf", headers=tourist_headers)
    assert r.status_code == 403
