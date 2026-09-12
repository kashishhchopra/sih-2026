"""Audit trail. It must record sensitive actions without ever joining -- or
breaking -- the caller's transaction."""
from app.models.audit import AuditLog
from app.services import audit


def test_failed_login_is_recorded(client, admin_user, db):
    client.post("/api/auth/login",
                data={"username": "admin@test.gov", "password": "wrongpass1"})
    row = db.query(AuditLog).filter_by(action="login").one()
    assert row.outcome == "failure"


def test_successful_login_is_recorded(client, admin_headers, db):
    row = db.query(AuditLog).filter_by(action="login", outcome="success").one()
    assert row.actor == "admin@test.gov"


def test_audit_does_not_commit_the_callers_transaction(db):
    """The regression test for the fix: `record` used to call db.commit() on the
    caller's session, prematurely persisting unrelated staged work."""
    from tests.conftest import make_tourist
    t = make_tourist(db)

    t.full_name = "UNCOMMITTED EDIT"          # staged, deliberately not committed
    audit.record(db, "some_action", actor="tester")
    db.rollback()                              # discard the staged edit

    db.refresh(t)
    assert t.full_name != "UNCOMMITTED EDIT", "audit leaked the caller's transaction"


def test_audit_failure_never_propagates(db, monkeypatch):
    import app.services.audit as audit_mod

    class Boom:
        def add(self, *_): raise RuntimeError("db down")
        def commit(self): raise RuntimeError("db down")
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(audit_mod, "SessionLocal", lambda: Boom())
    audit.record(db, "action", actor="tester")  # must not raise


def test_sos_is_audited(client, tourist_user, tourist_headers, db):
    from tests.conftest import make_unit
    make_unit(db)
    client.post(f"/api/tourists/{tourist_user.tourist_id}/sos",
                json={"lat": 26.1, "lng": 91.7, "message": "help"},
                headers=tourist_headers)
    assert db.query(AuditLog).filter_by(action="sos").count() == 1


def test_audit_log_endpoint_is_admin_only(client, tourist_headers, admin_headers):
    assert client.get("/api/audit-log", headers=tourist_headers).status_code == 403
    assert client.get("/api/audit-log", headers=admin_headers).status_code == 200
