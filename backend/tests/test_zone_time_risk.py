"""Time-aware zone risk: `zone_time_multiplier` and its use in scoring."""
import json

from app.services.safety import zone_time_multiplier
from tests.conftest import make_zone


def test_empty_curve_is_flat(db):
    z = make_zone(db)
    assert zone_time_multiplier(z, 3) == 1.0
    assert zone_time_multiplier(z, 22) == 1.0


def test_populated_curve_returns_hour_specific_multiplier(db):
    z = make_zone(db)
    z.time_risk_curve = json.dumps({"20": 1.4, "6": 0.6})
    assert zone_time_multiplier(z, 20) == 1.4
    assert zone_time_multiplier(z, 6) == 0.6
    # an hour absent from the curve still falls back to flat
    assert zone_time_multiplier(z, 12) == 1.0


def test_malformed_curve_falls_back_to_flat(db):
    z = make_zone(db)
    z.time_risk_curve = "{not valid json"
    assert zone_time_multiplier(z, 20) == 1.0

    z.time_risk_curve = json.dumps([1, 2, 3])  # valid JSON, wrong shape (not a dict)
    assert zone_time_multiplier(z, 20) == 1.0

    z.time_risk_curve = None
    assert zone_time_multiplier(z, 20) == 1.0
