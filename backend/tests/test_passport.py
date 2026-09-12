"""Digital Safety Passport + QR (services/passport.py, GET /tourists/{id}/passport)."""
from app.models.device import Device
from app.models.tourist import IdBlock
from tests.conftest import make_tourist


def test_passport_includes_essentials_and_qr(client, admin_headers, db):
    t = make_tourist(db)
    r = client.get(f"/api/tourists/{t.id}/passport", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["digital_id"] == t.digital_id
    assert body["emergency_contacts"]
    assert body["qr_png_base64"].startswith("data:image/png;base64,")
    assert body["device"] is None


def test_passport_includes_device_when_linked(client, admin_headers, db):
    t = make_tourist(db)
    db.add(Device(device_id="BAND-1", tourist_id=t.id, hashed_key="x", battery_pct=78.0))
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/passport", headers=admin_headers)
    assert r.json()["device"]["battery_pct"] == 78.0


def test_passport_visible_to_self(client, tourist_headers, tourist_user):
    r = client.get(f"/api/tourists/{tourist_user.tourist_id}/passport", headers=tourist_headers)
    assert r.status_code == 200


def test_passport_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Someone Else")
    r = client.get(f"/api/tourists/{other.id}/passport", headers=tourist_headers)
    assert r.status_code == 403


def test_passport_visible_to_responder(client, responder_headers, db):
    t = make_tourist(db)
    r = client.get(f"/api/tourists/{t.id}/passport", headers=responder_headers)
    assert r.status_code == 200


def test_passport_includes_consular_phone_for_foreign_nationals(client, admin_headers, db):
    t = make_tourist(db)
    t.nationality = "French"
    db.commit()
    r = client.get(f"/api/tourists/{t.id}/passport", headers=admin_headers)
    body = r.json()
    assert body["nationality_code"] == "FR"
    assert body["consular_phone"]


def test_passport_consular_phone_is_none_for_indian_nationals(client, admin_headers, db):
    t = make_tourist(db)
    r = client.get(f"/api/tourists/{t.id}/passport", headers=admin_headers)
    body = r.json()
    assert body["consular_phone"] is None


def test_scan_logs_chain_event(client, responder_headers, db):
    t = make_tourist(db)
    before = db.query(IdBlock).filter(IdBlock.tourist_id == t.id).count()

    r = client.post(f"/api/tourists/{t.id}/passport/scan", headers=responder_headers)
    assert r.status_code == 200

    after = db.query(IdBlock).filter(IdBlock.tourist_id == t.id).count()
    assert after == before + 1
    last = db.query(IdBlock).filter(IdBlock.tourist_id == t.id).order_by(IdBlock.index.desc()).first()
    assert last.event == "PASSPORT_SCANNED"
