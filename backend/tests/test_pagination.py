"""Bounded list queries: list_tourists / list_incidents no longer load an
entire table into Python per request."""
from tests.conftest import make_tourist, make_unit


def test_tourist_list_reports_total_count_header(client, admin_headers, db):
    for i in range(5):
        make_tourist(db, name=f"T{i}")
    r = client.get("/api/tourists", headers=admin_headers)
    assert r.headers["x-total-count"] == "5"
    assert len(r.json()) == 5


def test_tourist_list_respects_limit_and_offset(client, admin_headers, db):
    for i in range(5):
        make_tourist(db, name=f"T{i}")
    page1 = client.get("/api/tourists?limit=2&offset=0", headers=admin_headers).json()
    page2 = client.get("/api/tourists?limit=2&offset=2", headers=admin_headers).json()
    assert len(page1) == 2 and len(page2) == 2
    assert {t["id"] for t in page1}.isdisjoint({t["id"] for t in page2})


def test_tourist_list_limit_is_capped(client, admin_headers):
    r = client.get("/api/tourists?limit=10000", headers=admin_headers)
    assert r.status_code == 422


def test_tourist_list_default_limit_covers_typical_demo_data(client, admin_headers, db):
    for i in range(20):
        make_tourist(db, name=f"T{i}")
    r = client.get("/api/tourists", headers=admin_headers)
    assert len(r.json()) == 20  # well under the default limit of 200


def test_incident_list_pagination(client, admin_headers, db):
    from app.services.monitoring import trigger_sos
    make_unit(db)
    for i in range(5):
        trigger_sos(db, make_tourist(db, name=f"T{i}"), 26.1, 91.7, "help")

    r = client.get("/api/incidents?limit=2", headers=admin_headers)
    assert len(r.json()) == 2
    assert r.headers["x-total-count"] == "5"


def test_incident_list_pagination_combines_with_status_filter(client, admin_headers, db):
    from app.services.monitoring import trigger_sos
    make_unit(db)
    for i in range(4):
        trigger_sos(db, make_tourist(db, name=f"T{i}"), 26.1, 91.7, "help")

    r = client.get("/api/incidents?status=dispatched&limit=2", headers=admin_headers)
    assert r.headers["x-total-count"] == "4"
    assert len(r.json()) == 2


def test_negative_offset_rejected(client, admin_headers):
    assert client.get("/api/tourists?offset=-1", headers=admin_headers).status_code == 422


def test_zero_limit_rejected(client, admin_headers):
    assert client.get("/api/tourists?limit=0", headers=admin_headers).status_code == 422
