"""Crowd Density Detection (services/crowd_density.py)."""
from app.services.crowd_density import density_band, zone_density_report
from tests.conftest import make_tourist, make_zone


def test_density_band_thresholds():
    assert density_band(5) == "low"
    assert density_band(20) == "medium"
    assert density_band(50) == "high"


def test_zone_density_report_counts_tourists_inside_zone(db):
    zone = make_zone(db, name="Crowded Market", lat=26.165, lng=91.75, d=0.01)
    # Two tourists inside the zone, one far outside.
    make_tourist(db, name="A", lat=26.165, lng=91.75)
    make_tourist(db, name="B", lat=26.166, lng=91.751)
    make_tourist(db, name="Elsewhere", lat=10.0, lng=10.0)

    report = zone_density_report(db)
    entry = next(r for r in report if r["zone_id"] == zone.id)
    assert entry["tourist_count"] == 2
    assert entry["density"] == "low"
    assert entry["overcrowded"] is False


def test_zone_density_report_endpoint(client, admin_headers, db):
    make_zone(db)
    r = client.get("/api/zones/crowd-density", headers=admin_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_zone_density_report_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/zones/crowd-density", headers=tourist_headers)
    assert r.status_code == 403
