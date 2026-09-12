"""External Hash-Chain Anchoring (services/anchoring.py)."""
import json

from app.models.anchor import ChainAnchor
from app.services.anchoring import compute_root, publish_anchor, verify_anchor
from tests.conftest import make_tourist


def test_compute_root_changes_when_a_chain_grows(db):
    t = make_tourist(db)
    root1, count1, blocks1 = compute_root(db)

    from app.services import hashchain
    hashchain.append_block(db, t, "PASSPORT_SCANNED", {"x": 1})
    db.commit()

    root2, count2, blocks2 = compute_root(db)
    assert root1 != root2
    assert blocks2 > blocks1
    assert count1 == count2  # same tourist, more blocks -- not more tourists


def test_publish_anchor_writes_local_ledger_and_db_row(db, tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_LEDGER_PATH", str(ledger))
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_TARGET", "local")
    make_tourist(db)

    anchor = publish_anchor(db)

    assert anchor.id is not None
    assert anchor.anchor_target == "local"
    assert ledger.exists()
    lines = ledger.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["root_hash"] == anchor.root_hash
    assert record["receipt"] == anchor.external_ref


def test_verify_anchor_succeeds_against_matching_ledger(db, tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_LEDGER_PATH", str(ledger))
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_TARGET", "local")
    make_tourist(db)
    anchor = publish_anchor(db)

    result = verify_anchor(anchor)
    assert result["verified"] is True


def test_verify_anchor_fails_if_ledger_missing(db, tmp_path, monkeypatch):
    ledger = tmp_path / "does_not_exist.jsonl"
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_LEDGER_PATH", str(ledger))
    anchor = ChainAnchor(root_hash="abc", tourist_count=1, block_count=1,
                         anchor_target="local", external_ref="deadbeef")
    db.add(anchor)
    db.commit()
    db.refresh(anchor)

    result = verify_anchor(anchor)
    assert result["verified"] is False


def test_verify_anchor_fails_on_tampered_root(db, tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_LEDGER_PATH", str(ledger))
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_TARGET", "local")
    make_tourist(db)
    anchor = publish_anchor(db)

    # Simulate someone editing the DB row after the fact -- the external
    # ledger no longer matches, exactly the property this feature exists to
    # detect.
    anchor.root_hash = "tampered" * 8
    db.commit()

    result = verify_anchor(anchor)
    assert result["verified"] is False


# ---------------------------------------------------------------- endpoints
def test_anchor_endpoints(client, admin_headers, tmp_path, monkeypatch, db):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_LEDGER_PATH", str(ledger))
    monkeypatch.setattr("app.services.anchoring.settings.ANCHOR_TARGET", "local")
    make_tourist(db)

    created = client.post("/api/anchors", headers=admin_headers)
    assert created.status_code == 201
    aid = created.json()["id"]

    listed = client.get("/api/anchors", headers=admin_headers)
    assert len(listed.json()) == 1

    verified = client.get(f"/api/anchors/{aid}/verify", headers=admin_headers)
    assert verified.json()["verified"] is True


def test_anchor_endpoints_forbidden_for_tourist(client, tourist_headers):
    assert client.get("/api/anchors", headers=tourist_headers).status_code == 403
    assert client.post("/api/anchors", headers=tourist_headers).status_code == 403
