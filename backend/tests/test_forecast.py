"""Dynamic risk forecast: projected safety score at future horizons."""
from datetime import timedelta

from app.core.time import utc_now
from app.models.tourist import LocationPing
from app.services.forecast import forecast_risk
from app.services.trajectory import predict_trajectory
from tests.conftest import make_tourist, make_zone

_BASE_LAT, _BASE_LNG = 26.1000, 91.7000
_STEP = 0.001


def _history(db, tourist):
    """Five pings, one per minute, walking steadily north-east."""
    pings = []
    for i in range(5):
        p = LocationPing(
            tourist_id=tourist.id, lat=_BASE_LAT + i * _STEP, lng=_BASE_LNG + i * _STEP,
            speed_kmh=10, timestamp=utc_now() - timedelta(minutes=4 - i),
        )
        db.add(p)
        pings.append(p)
    db.commit()
    return pings


def test_forecast_returns_three_entries_for_default_horizons(db):
    t = make_tourist(db, lat=_BASE_LAT + 4 * _STEP, lng=_BASE_LNG + 4 * _STEP)
    _history(db, t)

    result = forecast_risk(db, t)

    assert len(result) == 3
    assert [f["minutes"] for f in result] == [15, 30, 60]
    for f in result:
        assert 0 <= f["score"] <= 100
        assert f["band"] in {"safe", "moderate", "risky", "danger"}


def test_forecast_works_with_no_ping_history(db):
    """No trajectory to extrapolate from -- still returns a forecast at the
    tourist's current position instead of crashing or dropping horizons."""
    t = make_tourist(db, lat=_BASE_LAT, lng=_BASE_LNG)
    result = forecast_risk(db, t)
    assert len(result) == 3


def test_forecast_trends_riskier_when_heading_toward_a_restricted_zone(db):
    t = make_tourist(db, lat=_BASE_LAT + 4 * _STEP, lng=_BASE_LNG + 4 * _STEP)
    pings = _history(db, t)

    # Find exactly where the +60min projection lands, and drop a restricted
    # zone right there so only the farthest-out horizon is affected.
    points = predict_trajectory(pings, horizon_min=60)
    far_point = next(p for p in points if p[2] == 60)
    make_zone(db, name="Danger Ahead", risk="restricted",
             lat=far_point[0], lng=far_point[1], d=0.003, crime=90)

    result = forecast_risk(db, t)
    by_minutes = {f["minutes"]: f for f in result}

    # band_for(): higher score = safer. Approaching a restricted zone should
    # make the +60min horizon score lower (riskier) than the +15min horizon.
    assert by_minutes[60]["score"] < by_minutes[15]["score"]
    assert by_minutes[60]["zone"] == "Danger Ahead"
    assert by_minutes[15]["zone"] == "open area"
