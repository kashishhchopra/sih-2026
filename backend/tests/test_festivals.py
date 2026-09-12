"""Festival & Local Event Intelligence (services/festival.py, /festivals, /festivals/near)."""
from datetime import date, timedelta

from app.models.festival import Festival


def _make_festival(db, name="Test Fest", days_from_today=10, lat=26.1445, lng=91.7362, recurring=True):
    start = date.today() + timedelta(days=days_from_today)
    f = Festival(
        name=name, description="A test festival", category="festival", state="Assam",
        lat=lat, lng=lng, start_date=start, end_date=start + timedelta(days=1),
        recurring_yearly=recurring, crowd_impact="high",
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def test_list_festivals_within_days(client, admin_headers, db):
    _make_festival(db, name="Soon", days_from_today=5)
    _make_festival(db, name="Far Off", days_from_today=200)

    r = client.get("/api/festivals", headers=admin_headers, params={"within_days": 30})
    names = [f["name"] for f in r.json()]
    assert "Soon" in names
    assert "Far Off" not in names


def test_festivals_near_filters_by_distance(client, admin_headers, db):
    _make_festival(db, name="Nearby", lat=26.1445, lng=91.7362)
    _make_festival(db, name="Distant", lat=30.0, lng=95.0)

    r = client.get("/api/festivals/near", headers=admin_headers,
                   params={"lat": 26.1445, "lng": 91.7362, "radius_km": 50})
    names = [f["name"] for f in r.json()]
    assert "Nearby" in names
    assert "Distant" not in names


def test_recurring_festival_resolves_to_next_occurrence_not_a_past_one(db):
    from app.services.festival import list_festivals

    past_year_festival = Festival(
        name="Annual Fest", description="", category="festival", state=None,
        lat=26.1445, lng=91.7362, start_date=date(2020, 3, 1), end_date=date(2020, 3, 3),
        recurring_yearly=True, crowd_impact="medium",
    )
    db.add(past_year_festival)
    db.commit()

    results = list_festivals(db, within_days=400)
    fest = next(f for f in results if f["name"] == "Annual Fest")
    # Must resolve forward to a real upcoming date, never stay stuck in 2020.
    assert fest["next_start"] >= date.today().isoformat()


def test_public_holiday_category_returns_empty_without_an_api_key(client, admin_headers):
    # CALENDARIFIC_API_KEY is blank in tests (see settings default) -- the
    # holiday signal must be absent, never fabricated.
    r = client.get("/api/festivals", headers=admin_headers, params={"category": "public_holiday"})
    assert r.status_code == 200
    assert r.json() == []
