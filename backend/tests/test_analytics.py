"""Analytics aggregation. These moved from Python loops into SQL, and zone
attribution moved from substring-matching messages onto a real foreign key."""
from app.services.monitoring import process_ping, trigger_sos
from tests.conftest import make_station, make_tourist, make_unit, make_zone


def test_summary_on_empty_database(client, admin_headers):
    body = client.get("/api/analytics/summary", headers=admin_headers).json()
    assert body["total_tourists"] == 0
    assert body["avg_safety_score"] == 0
    assert body["avg_response_time_seconds"] == 0


def test_summary_counts_statuses(client, admin_headers, db):
    make_unit(db)
    make_tourist(db, name="Safe One")
    t2 = make_tourist(db, name="In Trouble")
    trigger_sos(db, t2, 26.1445, 91.7362, "help")

    body = client.get("/api/analytics/summary", headers=admin_headers).json()
    assert body["total_tourists"] == 2
    assert body["sos_active"] == 1
    assert body["open_incidents"] == 1
    assert 0 <= body["avg_safety_score"] <= 100


def test_zone_risk_uses_the_foreign_key_not_message_text(client, admin_headers, db):
    """Two zones where one name contains the other: substring matching would
    have credited the alert to both."""
    make_zone(db, name="Market", risk="high", lat=26.165, lng=91.75, d=0.004)
    make_zone(db, name="Old Market", risk="high", lat=27.50, lng=92.50, d=0.004)
    t = make_tourist(db, itinerary=[{"name": "Stop", "lat": 26.165, "lng": 91.75}])
    process_ping(db, t, 26.165, 91.75, speed_kmh=3)

    rows = {r["zone"]: r["alert_count"]
            for r in client.get("/api/analytics/zone-risk", headers=admin_headers).json()}
    assert rows["Market"] == 1
    assert rows["Old Market"] == 0, "alert was misattributed to the other zone"


def test_alerts_by_type(client, admin_headers, db):
    make_unit(db)
    t = make_tourist(db)
    trigger_sos(db, t, 26.1445, 91.7362, "help")
    rows = {r["type"]: r["count"]
            for r in client.get("/api/analytics/alerts-by-type",
                                headers=admin_headers).json()}
    assert rows["sos"] == 1


def test_severity_breakdown_is_ordered(client, admin_headers, db):
    make_unit(db)
    trigger_sos(db, make_tourist(db), 26.1445, 91.7362, "help")
    rows = client.get("/api/analytics/severity-breakdown", headers=admin_headers).json()
    order = ["low", "medium", "high", "critical"]
    seen = [r["severity"] for r in rows]
    assert seen == sorted(seen, key=order.index)


def test_incidents_over_time_groups_by_day(client, admin_headers, db):
    make_unit(db)
    trigger_sos(db, make_tourist(db), 26.1445, 91.7362, "help")
    rows = client.get("/api/analytics/incidents-over-time",
                      headers=admin_headers).json()
    assert len(rows) == 1 and rows[0]["count"] == 1


def test_analytics_requires_admin(client, tourist_headers):
    for ep in ["summary", "alerts-by-type", "incidents-over-time",
               "zone-risk", "severity-breakdown"]:
        assert client.get(f"/api/analytics/{ep}",
                          headers=tourist_headers).status_code == 403


# ---------------- new: incidents-over-time granularity ----------------

def test_incidents_over_time_defaults_to_daily(client, admin_headers, db):
    t = make_tourist(db)
    trigger_sos(db, t, 26.1445, 91.7362, "help")
    rows = client.get("/api/analytics/incidents-over-time", headers=admin_headers).json()
    assert len(rows) == 1
    assert len(rows[0]["date"]) == 10  # YYYY-MM-DD


def test_incidents_over_time_weekly_and_monthly_rebucket_the_same_rows(client, admin_headers, db):
    t = make_tourist(db)
    trigger_sos(db, t, 26.1445, 91.7362, "help")
    daily = client.get("/api/analytics/incidents-over-time", headers=admin_headers).json()
    weekly = client.get("/api/analytics/incidents-over-time?granularity=week",
                        headers=admin_headers).json()
    monthly = client.get("/api/analytics/incidents-over-time?granularity=month",
                         headers=admin_headers).json()
    assert sum(r["count"] for r in daily) == sum(r["count"] for r in weekly) == sum(r["count"] for r in monthly)
    assert "W" in weekly[0]["date"]
    assert len(monthly[0]["date"]) == 7  # YYYY-MM


def test_pdf_report_unaffected_by_the_granularity_parameter(client, admin_headers, db):
    # Regression: incidents_over_time() gained a leading `granularity` param;
    # a direct Python call that doesn't pass it explicitly would receive
    # FastAPI's Query() sentinel object instead of the string "day" and
    # crash instead of rendering.
    t = make_tourist(db)
    trigger_sos(db, t, 26.1445, 91.7362, "help")
    r = client.get("/api/analytics/pdf", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


# ---------------- incident-types ----------------

def test_incident_types_counts_and_sos_breakdown(client, admin_headers, db):
    t1, t2 = make_tourist(db, name="A"), make_tourist(db, name="B")
    trigger_sos(db, t1, 26.1445, 91.7362, "help")
    inc2 = trigger_sos(db, t2, 26.1445, 91.7362, "help")

    from app.models.incident import Incident
    db.get(Incident, inc2["incident_id"]).status = "resolved"
    db.commit()

    body = client.get("/api/analytics/incident-types", headers=admin_headers).json()
    assert {"type": "sos", "count": 2} in body["by_type"]
    assert body["sos"] == {"total": 2, "active": 1, "resolved": 1}


def test_incident_types_on_empty_database(client, admin_headers):
    body = client.get("/api/analytics/incident-types", headers=admin_headers).json()
    assert body == {"by_type": [], "sos": {"total": 0, "active": 0, "resolved": 0}}


# ---------------- incidents-heatmap ----------------

def test_heatmap_returns_located_incidents_only(client, admin_headers, db):
    t = make_tourist(db)
    trigger_sos(db, t, 26.1445, 91.7362, "help")
    rows = client.get("/api/analytics/incidents-heatmap", headers=admin_headers).json()
    assert rows == [{"lat": 26.1445, "lng": 91.7362}]


def test_heatmap_on_empty_database(client, admin_headers):
    assert client.get("/api/analytics/incidents-heatmap", headers=admin_headers).json() == []


# ---------------- police-performance ----------------

def test_police_performance_counts_cases_and_response_time(client, admin_headers, db):
    from app.services import police_network
    zone = make_zone(db, name="Zone A")
    station = make_station(db, name="Station A", zone_id=zone.id)
    t = make_tourist(db, itinerary=[{"name": "Stop", "lat": zone.polygon and 26.165 or 26.165,
                                     "lng": 91.75}])
    result = trigger_sos(db, t, 26.165, 91.75, "help")
    from app.models.incident import Incident
    inc = db.get(Incident, result["incident_id"])
    inc.station_id = station.id
    from app.core.time import utc_now
    from datetime import timedelta
    inc.dispatched_at = inc.detected_at + timedelta(seconds=30)
    inc.resolved_at = inc.detected_at + timedelta(minutes=10)
    inc.status = "resolved"
    db.commit()

    body = client.get("/api/analytics/police-performance", headers=admin_headers).json()
    row = next(r for r in body["stations"] if r["station_id"] == station.id)
    assert row["cases_handled"] == 1
    assert row["resolved"] == 1
    assert row["pending"] == 0
    assert row["avg_response_time_seconds"] == 30.0
    assert row["avg_resolution_time_seconds"] == 600.0


def test_police_performance_counts_inter_station_transfers(client, admin_headers, db):
    from app.services import police_network
    z1 = make_zone(db, name="Z1")
    z2 = make_zone(db, name="Z2", lat=27.0)
    s1 = make_station(db, name="S1", zone_id=z1.id)
    s2 = make_station(db, name="S2", zone_id=z2.id)
    t = make_tourist(db)
    result = trigger_sos(db, t, 26.1445, 91.7362, "help")
    from app.models.incident import Incident
    inc = db.get(Incident, result["incident_id"])
    inc.station_id = s1.id
    db.commit()
    police_network.forward_incident(db, inc, s2.id, note="test", actor="admin")
    db.commit()

    body = client.get("/api/analytics/police-performance", headers=admin_headers).json()
    assert body["total_transfers"] == 1
    row = next(r for r in body["stations"] if r["station_id"] == s2.id)
    assert row["transfers_received"] == 1


def test_police_performance_station_with_no_cases_reports_nulls_not_zero_averages(
        client, admin_headers, db):
    make_station(db, name="Idle Station")
    body = client.get("/api/analytics/police-performance", headers=admin_headers).json()
    row = body["stations"][0]
    assert row["cases_handled"] == 0
    assert row["avg_response_time_seconds"] is None
    assert row["avg_resolution_time_seconds"] is None


# ---------------- tourist-activity ----------------

def test_tourist_activity_domestic_vs_international(client, admin_headers, db):
    make_tourist(db, name="Domestic")  # default document_type="aadhaar"
    foreign = make_tourist(db, name="Foreign")
    foreign.document_type = "passport"
    db.commit()

    body = client.get("/api/analytics/tourist-activity", headers=admin_headers).json()
    assert body["total_tourists"] == 2
    assert body["domestic_tourists"] == 1
    assert body["international_tourists"] == 1


def test_tourist_activity_popular_destinations_from_confirmed_itineraries(
        client, admin_headers, db):
    import json as json_mod
    from app.models.itinerary import ItineraryDocument
    t = make_tourist(db)
    doc = ItineraryDocument(
        tourist_id=t.id, filename="trip.pdf", status="extracted", confirmed=True,
        extracted_json=json_mod.dumps({"destinations": [
            {"name": "Kaziranga National Park", "lat": 26.58, "lng": 93.17},
            {"name": "Kamakhya Temple", "lat": 26.16, "lng": 91.71},
        ]}),
    )
    db.add(doc)
    db.commit()

    body = client.get("/api/analytics/tourist-activity", headers=admin_headers).json()
    names = {r["destination"] for r in body["popular_destinations"]}
    assert names == {"Kaziranga National Park", "Kamakhya Temple"}


def test_tourist_activity_ignores_unconfirmed_itineraries(client, admin_headers, db):
    import json as json_mod
    from app.models.itinerary import ItineraryDocument
    t = make_tourist(db)
    db.add(ItineraryDocument(
        tourist_id=t.id, filename="trip.pdf", status="extracted", confirmed=False,
        extracted_json=json_mod.dumps({"destinations": [{"name": "Should Not Appear"}]}),
    ))
    db.commit()
    body = client.get("/api/analytics/tourist-activity", headers=admin_headers).json()
    assert body["popular_destinations"] == []


def test_tourist_activity_on_empty_database(client, admin_headers):
    body = client.get("/api/analytics/tourist-activity", headers=admin_headers).json()
    assert body["total_tourists"] == 0
    assert body["popular_destinations"] == []


# ---------------- Excel export ----------------

def test_excel_report_downloads_a_real_workbook(client, admin_headers, db):
    t = make_tourist(db)
    trigger_sos(db, t, 26.1445, 91.7362, "help")
    r = client.get("/api/analytics/excel", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    # A real .xlsx is a zip archive -- starts with the PK signature.
    assert r.content[:2] == b"PK"

    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    assert set(wb.sheetnames) == {
        "Summary", "Incidents Over Time", "Incident Types", "Alerts by Type",
        "Zone Risk", "Severity Breakdown", "Police Performance", "Tourist Activity",
    }


def test_excel_report_requires_admin(client, tourist_headers):
    assert client.get("/api/analytics/excel", headers=tourist_headers).status_code == 403


# ---------------- new endpoints require admin ----------------

def test_new_analytics_endpoints_require_admin(client, tourist_headers):
    for path in ("/api/analytics/police-performance", "/api/analytics/tourist-activity",
                "/api/analytics/incident-types", "/api/analytics/incidents-heatmap"):
        assert client.get(path, headers=tourist_headers).status_code == 403, path
