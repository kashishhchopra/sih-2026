"""Real POI import from the committed OSM snapshot (app/services/poi.py)."""
from app.models.police import PoliceUnit
from app.services import poi

FIXTURE_UNITS = [
    {"osm_id": 111, "name": "Test Police Station", "unit_type": "police",
     "lat": 26.15, "lng": 91.74, "phone": "100", "station": "Test Police Station"},
    {"osm_id": 222, "name": "Test Hospital", "unit_type": "ambulance",
     "lat": 26.16, "lng": 91.75, "phone": "102", "station": "Test Hospital"},
]


def test_load_snapshot_returns_empty_list_when_no_file(monkeypatch, tmp_path):
    monkeypatch.setattr(poi, "_SNAPSHOT_PATH", tmp_path / "does-not-exist.json")
    assert poi.load_snapshot() == []


def test_seed_units_from_snapshot_creates_rows(db, monkeypatch):
    monkeypatch.setattr(poi, "load_snapshot", lambda: FIXTURE_UNITS)
    written = poi.seed_units_from_snapshot(db)
    db.commit()

    assert written == 2
    rows = db.query(PoliceUnit).filter(PoliceUnit.source == "osm").all()
    assert len(rows) == 2
    names = {r.name for r in rows}
    assert names == {"Test Police Station", "Test Hospital"}


def test_seed_units_from_snapshot_upserts_on_rerun(db, monkeypatch):
    monkeypatch.setattr(poi, "load_snapshot", lambda: FIXTURE_UNITS)
    poi.seed_units_from_snapshot(db)
    db.commit()

    updated = [dict(FIXTURE_UNITS[0], name="Renamed Police Station"), FIXTURE_UNITS[1]]
    monkeypatch.setattr(poi, "load_snapshot", lambda: updated)
    written = poi.seed_units_from_snapshot(db)
    db.commit()

    assert written == 2
    assert db.query(PoliceUnit).filter(PoliceUnit.source == "osm").count() == 2  # no duplicates
    renamed = db.query(PoliceUnit).filter(PoliceUnit.osm_id == 111).one()
    assert renamed.name == "Renamed Police Station"


def test_seed_units_returns_zero_for_empty_snapshot(db, monkeypatch):
    monkeypatch.setattr(poi, "load_snapshot", lambda: [])
    assert poi.seed_units_from_snapshot(db) == 0


def test_malformed_rows_are_skipped_not_fatal(db, monkeypatch):
    monkeypatch.setattr(poi, "load_snapshot", lambda: [
        {"osm_id": 333, "name": None, "lat": 1.0, "lng": 1.0},  # missing name
        FIXTURE_UNITS[0],
    ])
    written = poi.seed_units_from_snapshot(db)
    db.commit()
    assert written == 1
