"""Digital Tourist Safety ID: secure QR/token issuance, verification,
role-based scan access, regeneration/invalidation, and scan audit trail.
(services/tourist_id.py, app/api/tourist_id.py)
"""
from datetime import timedelta

from app.core.time import utc_now
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.tourist_id import TouristIdScan, TouristIdToken
from app.services import tourist_id
from app.services.monitoring import trigger_sos
from tests.conftest import make_station, make_tourist, make_unit, make_zone


# ---------------------------------------------------------------- registration
def test_registration_accepts_photo_and_hotel(client):
    r = client.post("/api/tourists", json={
        "full_name": "Kashish Chopra", "document_type": "aadhaar",
        "document_number": "123456789999", "phone": "9876543212",
        "photo": "data:image/png;base64,iVBORw0KGgo=", "hotel": "ABC Residency",
        "trip_start": "2026-01-01T00:00:00", "trip_end": "2026-01-10T00:00:00",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["photo"] == "data:image/png;base64,iVBORw0KGgo="
    assert body["hotel"] == "ABC Residency"
    assert body["digital_id"].startswith("STS-")


# ---------------------------------------------------------------- digital-id card
def test_digital_id_auto_issues_token_and_returns_qr(client, admin_headers, db):
    t = make_tourist(db)
    r = client.get(f"/api/tourists/{t.id}/digital-id", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["digital_id"] == t.digital_id
    assert body["id_status"] == "active"
    assert body["qr_png_base64"].startswith("data:image/png;base64,")
    assert db.query(TouristIdToken).filter(TouristIdToken.tourist_id == t.id).count() == 1


def test_digital_id_visible_to_self_not_to_other_tourist(client, tourist_headers, tourist_user, db):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/digital-id", headers=tourist_headers)
    assert r.status_code == 200

    other = make_tourist(db, name="Someone Else")
    r2 = client.get(f"/api/tourists/{other.id}/digital-id", headers=tourist_headers)
    assert r2.status_code == 403


def test_digital_id_status_expired_for_past_trip(client, admin_headers, db):
    t = make_tourist(db)
    now = utc_now()
    t.trip_start = now - timedelta(days=10)
    t.trip_end = now - timedelta(days=1)
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/digital-id", headers=admin_headers)
    assert r.json()["id_status"] == "expired"


def test_digital_id_status_expiring_soon(client, admin_headers, db):
    t = make_tourist(db)
    now = utc_now()
    t.trip_start = now - timedelta(days=1)
    t.trip_end = now + timedelta(hours=2)
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/digital-id", headers=admin_headers)
    assert r.json()["id_status"] == "expiring_soon"


# ---------------------------------------------------------------- regeneration
def test_regenerate_invalidates_old_token(client, admin_headers, db):
    t = make_tourist(db)
    _, old_raw = tourist_id.issue_token(db, t)
    db.commit()

    r = client.post(f"/api/tourists/{t.id}/digital-id/regenerate", headers=admin_headers)
    assert r.status_code == 200
    new_qr = r.json()["qr_png_base64"]
    assert new_qr

    # old token must no longer verify
    result = tourist_id.scan(db, _admin_user(db), token_raw=old_raw)
    assert result["verification_status"] == "invalidated"

    assert db.query(TouristIdToken).filter(
        TouristIdToken.tourist_id == t.id, TouristIdToken.status == "active"
    ).count() == 1


def test_suspend_then_reactivate(client, admin_headers, db):
    t = make_tourist(db)
    row, raw = tourist_id.issue_token(db, t)
    db.commit()

    r = client.post(f"/api/tourists/{t.id}/digital-id/suspend", headers=admin_headers)
    assert r.status_code == 204
    result = tourist_id.scan(db, _admin_user(db), token_raw=raw)
    assert result["verification_status"] == "invalidated"

    r2 = client.post(f"/api/tourists/{t.id}/digital-id/reactivate", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["id_status"] == "active"


# ---------------------------------------------------------------- scan / verify
def _admin_user(db):
    from app.models.user import User
    return db.query(User).filter(User.role == "admin").first()


def test_scan_by_qr_token_police_tier(client, admin_headers, db):
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    client.get(f"/api/tourists/{t.id}/digital-id", headers=admin_headers)  # auto-issues a token
    qr_payload = "TSID:" + _extract_raw_from_card(db, t)

    r2 = client.post("/api/tourist-id/scan", json={"token": qr_payload}, headers=admin_headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["verification_status"] == "verified"
    assert body["digital_id"] == t.digital_id
    assert "emergency_contacts" in body
    assert "active_incidents" in body
    assert "document_number" not in body


def _extract_raw_from_card(db, tourist):
    """Test helper: read the (encrypted-at-rest, decrypted-on-read) raw token
    directly, since the API never re-exposes it outside the QR image."""
    row = (
        db.query(TouristIdToken)
        .filter(TouristIdToken.tourist_id == tourist.id, TouristIdToken.status == "active")
        .order_by(TouristIdToken.issued_at.desc())
        .first()
    )
    return row.raw_token_encrypted


def test_scan_by_manual_digital_id(client, admin_headers, db):
    t = make_tourist(db)
    tourist_id.issue_token(db, t)
    db.commit()
    r = client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["verification_status"] == "verified"


def test_scan_unknown_token_not_found(client, admin_headers):
    r = client.post("/api/tourist-id/scan", json={"token": "TSID:doesnotexist"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["verification_status"] == "not_found"


def test_scan_requires_token_or_digital_id(client, admin_headers):
    r = client.post("/api/tourist-id/scan", json={}, headers=admin_headers)
    assert r.status_code == 400


def test_scan_forbidden_for_tourist_role(client, tourist_headers):
    r = client.post("/api/tourist-id/scan", json={"digital_id": "STS-ANY"}, headers=tourist_headers)
    assert r.status_code == 403


def test_scan_expired_trip(client, admin_headers, db):
    t = make_tourist(db)
    tourist_id.issue_token(db, t)
    now = utc_now()
    t.trip_start = now - timedelta(days=10)
    t.trip_end = now - timedelta(days=1)
    db.commit()
    r = client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)
    assert r.json()["verification_status"] == "expired"


# ---------------------------------------------------------------- role-based access
def test_police_scan_includes_zone_and_station(client, admin_headers, db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    make_station(db, name="Market PS", zone_id=zone.id, lat=26.165, lng=91.75)
    t = make_tourist(db, lat=26.165, lng=91.75)
    tourist_id.issue_token(db, t)
    db.commit()

    r = client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)
    body = r.json()
    assert body["current_zone"]["name"] == zone.name
    assert body["assigned_station"]["name"] == "Market PS"


# ---------------------------------------------------------------- SOS integration
def test_sos_incident_visible_via_scan(client, admin_headers, db):
    make_unit(db)
    t = make_tourist(db)
    tourist_id.issue_token(db, t)
    db.commit()
    trigger_sos(db, t, t.last_lat, t.last_lng, "help")

    r = client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)
    body = r.json()
    assert len(body["active_incidents"]) == 1
    assert body["active_incidents"][0]["type"] == "sos"


# ---------------------------------------------------------------- audit trail
def test_scan_writes_structured_scan_row_and_generic_audit_log(client, admin_headers, db):
    t = make_tourist(db)
    tourist_id.issue_token(db, t)
    db.commit()

    client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)

    scan_row = db.query(TouristIdScan).filter(TouristIdScan.tourist_id == t.id).first()
    assert scan_row is not None
    assert scan_row.verification_status == "verified"
    assert scan_row.scanner_role == "admin"

    audit_row = db.query(AuditLog).filter(
        AuditLog.action == "qr_scan", AuditLog.target == t.digital_id
    ).first()
    assert audit_row is not None
    assert audit_row.outcome == "verified"


def test_id_scans_endpoint_lists_history(client, admin_headers, db):
    t = make_tourist(db)
    tourist_id.issue_token(db, t)
    db.commit()
    client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)

    r = client.get(f"/api/tourists/{t.id}/id-scans", headers=admin_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["verification_status"] == "verified"
    assert isinstance(rows[0]["accessed_fields"], list)


# ---------------------------------------------------------------- incident from scan
def test_report_incident_from_scan(client, admin_headers, db):
    zone = make_zone(db, lat=26.165, lng=91.75, d=0.008)
    make_station(db, name="Market PS", zone_id=zone.id, lat=26.165, lng=91.75)
    t = make_tourist(db, lat=26.165, lng=91.75)

    r = client.post("/api/tourist-id/report-incident", json={
        "digital_id": t.digital_id, "description": "Found disoriented near market", "severity": "high",
    }, headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "detected"

    inc = db.get(Incident, body["incident_id"])
    assert inc.tourist_id == t.id
    assert inc.type == "field_report"
    assert inc.severity == "high"
    assert inc.station_id is not None


# ---------------------------------------------------------------- photo update
def test_update_photo_self(client, tourist_headers, tourist_user):
    r = client.patch(f"/api/tourists/{tourist_user.tourist_id}/photo",
                     json={"photo": "data:image/png;base64,abcd"}, headers=tourist_headers)
    assert r.status_code == 204


def test_my_recent_scans(client, admin_headers, db):
    t = make_tourist(db)
    tourist_id.issue_token(db, t)
    db.commit()
    client.post("/api/tourist-id/scan", json={"digital_id": t.digital_id}, headers=admin_headers)
    client.post("/api/tourist-id/scan", json={"digital_id": "STS-NOPE"}, headers=admin_headers)

    r = client.get("/api/tourist-id/scans/mine", headers=admin_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert rows[0]["verification_status"] == "not_found"
    assert rows[1]["verification_status"] == "verified"
    assert rows[1]["full_name"] == t.full_name
