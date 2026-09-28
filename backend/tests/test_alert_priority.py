"""AI Alert Prioritization: ranking layer over existing alerts (services/alert_priority.py)."""
from app.models.alert import Alert
from app.services.alert_priority import bucket, prioritize, score_alert
from tests.conftest import make_tourist, make_zone


def _alert(**kw):
    defaults = {"type": "anomaly", "severity": "medium", "message": "m", "lat": 1.0, "lng": 1.0}
    defaults.update(kw)
    return Alert(**defaults)


def test_score_alert_weighs_severity_type_and_zone():
    from app.models.zone import Zone

    low = score_alert(_alert(type="route_deviation", severity="low"), None)
    critical = score_alert(
        _alert(type="sos", severity="critical"), Zone(name="Z", risk_level="restricted",
                                                       polygon="[]")
    )
    assert critical > low


def test_bucket_thresholds():
    assert bucket(60) == "critical"
    assert bucket(40) == "high"
    assert bucket(25) == "medium"
    assert bucket(5) == "low"


def test_prioritize_sorts_highest_first():
    alerts = [
        _alert(type="route_deviation", severity="low"),
        _alert(type="sos", severity="critical"),
        _alert(type="geofence", severity="high"),
    ]
    ranked = prioritize(alerts, {})
    scores = [r["priority_score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0]["alert"].type == "sos"
    assert ranked[0]["priority"] == "critical"


# ---------------------------------------------------------------- endpoint
def test_prioritized_alerts_endpoint(client, admin_headers, db):
    t = make_tourist(db)
    z = make_zone(db, risk="restricted")
    db.add_all([
        Alert(tourist_id=t.id, type="route_deviation", severity="low", message="m1"),
        Alert(tourist_id=t.id, type="sos", severity="critical", zone_id=z.id, message="m2"),
    ])
    db.commit()

    r = client.get("/api/alerts/prioritized", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["priority"] == "critical"
    assert body[0]["priority_score"] >= body[1]["priority_score"]


def test_prioritized_alerts_forbidden_for_tourist(client, tourist_headers):
    r = client.get("/api/alerts/prioritized", headers=tourist_headers)
    assert r.status_code == 403
