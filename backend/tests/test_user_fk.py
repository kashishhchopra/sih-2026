"""users.tourist_id / users.unit_id foreign key enforcement."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_password
from app.models.user import User
from tests.conftest import make_tourist, make_unit


def test_user_tourist_id_accepts_a_real_tourist(db):
    t = make_tourist(db)
    u = User(email="a@b.com", full_name="A", hashed_password=hash_password("x1234567"),
              role="tourist", tourist_id=t.id)
    db.add(u)
    db.commit()  # should not raise
    assert u.tourist_id == t.id


def test_user_tourist_id_rejects_a_nonexistent_tourist(db):
    u = User(email="a@b.com", full_name="A", hashed_password=hash_password("x1234567"),
              role="tourist", tourist_id=999999)
    db.add(u)
    with pytest.raises(IntegrityError):
        db.commit()


def test_user_unit_id_accepts_a_real_unit(db):
    unit = make_unit(db)
    u = User(email="r@b.com", full_name="R", hashed_password=hash_password("x1234567"),
              role="responder", unit_id=unit.id)
    db.add(u)
    db.commit()
    assert u.unit_id == unit.id


def test_user_unit_id_rejects_a_nonexistent_unit(db):
    u = User(email="r@b.com", full_name="R", hashed_password=hash_password("x1234567"),
              role="responder", unit_id=999999)
    db.add(u)
    with pytest.raises(IntegrityError):
        db.commit()


def test_user_has_sessions_valid_from_default(db):
    u = User(email="c@b.com", full_name="C", hashed_password=hash_password("x1234567"), role="admin")
    db.add(u)
    db.commit()
    db.refresh(u)
    assert u.sessions_valid_from is not None
