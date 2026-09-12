"""Digital-ID hash chain: the tamper-evidence the project's headline claim rests on.

The original `verify_chain` computed the expected hash and never compared it, so
content tampering went undetected. These are the regression tests for that.
"""
import hashlib
import json

import pytest

from app.models.tourist import IdBlock
from app.services import hashchain
from tests.conftest import make_tourist


def test_genesis_block_links_to_zero_hash(db):
    t = make_tourist(db)
    b = db.query(IdBlock).filter_by(tourist_id=t.id, index=0).one()
    assert b.previous_hash == hashchain.GENESIS_HASH
    assert b.index == 0


def test_appending_links_blocks_in_order(db):
    t = make_tourist(db)
    hashchain.append_block(db, t, "CHECKIN", {"where": "hotel"})
    hashchain.append_block(db, t, "CHECKOUT", {"where": "hotel"})
    db.commit()

    blocks = db.query(IdBlock).filter_by(tourist_id=t.id).order_by(IdBlock.index).all()
    assert [b.index for b in blocks] == [0, 1, 2]
    # Deliberately unequal lengths: pair each block with its successor.
    for prev, cur in zip(blocks, blocks[1:], strict=False):
        assert cur.previous_hash == prev.hash


def test_clean_chain_verifies(db):
    t = make_tourist(db)
    hashchain.append_block(db, t, "CHECKIN", {"where": "hotel"})
    db.commit()
    assert hashchain.verify_chain(db, t.id) == {
        "valid": True, "blocks": 2, "broken_at": None, "reason": None
    }


def test_editing_block_data_is_detected(db):
    """The exact bug that was fixed: mutating `data` must invalidate the chain."""
    t = make_tourist(db)
    hashchain.append_block(db, t, "CHECKIN", {"where": "hotel"})
    db.commit()

    b = db.query(IdBlock).filter_by(tourist_id=t.id, index=1).one()
    b.data = json.dumps({"where": "FORGED LOCATION"})
    db.commit()

    result = hashchain.verify_chain(db, t.id)
    assert result["valid"] is False
    assert result["broken_at"] == 1
    assert "content hash" in result["reason"]


def test_editing_block_event_is_detected(db):
    t = make_tourist(db)
    db.commit()
    b = db.query(IdBlock).filter_by(tourist_id=t.id, index=0).one()
    b.event = "ID_REVOKED"
    db.commit()
    assert hashchain.verify_chain(db, t.id)["valid"] is False


def test_attacker_cannot_forge_hash_without_the_key(db):
    """Digests are keyed (HMAC). An attacker with database write access but no
    SECRET_KEY cannot recompute a digest that verifies -- this is what protects
    the newest block, which no later block pins."""
    t = make_tourist(db)
    db.commit()
    b = db.query(IdBlock).filter_by(tourist_id=t.id, index=0).one()
    b.data = json.dumps({"digital_id": "STS-FORGED"})
    payload = f"{b.index}|{b.hashed_at}|{b.event}|{b.data}|{b.previous_hash}"
    b.hash = hashlib.sha256(payload.encode()).hexdigest()  # unkeyed guess
    db.commit()

    assert hashchain.verify_chain(db, t.id)["valid"] is False


def test_deleting_a_block_is_detected(db):
    t = make_tourist(db)
    hashchain.append_block(db, t, "CHECKIN", {"a": 1})
    hashchain.append_block(db, t, "CHECKOUT", {"a": 2})
    db.commit()

    db.query(IdBlock).filter_by(tourist_id=t.id, index=1).delete()
    db.commit()

    result = hashchain.verify_chain(db, t.id)
    assert result["valid"] is False
    assert "index gap" in result["reason"]


def test_relinking_after_deletion_still_fails(db):
    """Splicing out a block and repairing the link must still fail, because the
    repaired block's own digest no longer matches its contents."""
    t = make_tourist(db)
    hashchain.append_block(db, t, "CHECKIN", {"a": 1})
    hashchain.append_block(db, t, "CHECKOUT", {"a": 2})
    db.commit()

    genesis = db.query(IdBlock).filter_by(tourist_id=t.id, index=0).one()
    db.query(IdBlock).filter_by(tourist_id=t.id, index=1).delete()
    last = db.query(IdBlock).filter_by(tourist_id=t.id, index=2).one()
    last.index = 1
    last.previous_hash = genesis.hash
    db.commit()

    assert hashchain.verify_chain(db, t.id)["valid"] is False


def test_empty_chain_is_trivially_valid(db):
    assert hashchain.verify_chain(db, 999)["valid"] is True


@pytest.mark.parametrize("event", ["ID_ISSUED", "CHECKIN", "EFIR_FILED"])
def test_data_round_trips_through_the_chain(db, event):
    t = make_tourist(db)
    payload = {"nested": {"x": 1}, "list": [1, 2, 3], "unicode": "Guwahati"}
    b = hashchain.append_block(db, t, event, payload)
    db.commit()
    assert json.loads(b.data) == payload
    assert hashchain.verify_chain(db, t.id)["valid"] is True
