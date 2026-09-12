"""Voice-guidance navigation (services/navigation.py)."""
from app.services.navigation import get_navigation_guidance
from tests.conftest import make_tourist


def test_no_destination_when_itinerary_is_empty(db):
    t = make_tourist(db, itinerary=[])
    result = get_navigation_guidance(t)
    assert result == {"has_destination": False}


def test_no_destination_when_no_last_location(db):
    t = make_tourist(db)
    t.last_lat = None
    t.last_lng = None
    db.commit()
    result = get_navigation_guidance(t)
    assert result["has_destination"] is False


def test_guidance_toward_a_distant_destination(db):
    # Guwahati -> Kamakhya Temple, a real few-km hop.
    t = make_tourist(db, lat=26.1445, lng=91.7362,
                     itinerary=[{"name": "Kamakhya Temple", "lat": 26.1664, "lng": 91.7050}])
    result = get_navigation_guidance(t)
    assert result["has_destination"] is True
    assert result["destination_name"] == "Kamakhya Temple"
    assert result["distance_km"] > 0
    assert result["eta_minutes"] > 0
    assert result["demo"] is True  # no GOOGLE_MAPS_API_KEY in tests
    assert "Kamakhya Temple" in result["instruction"]
    assert result["arrived"] is False
    assert result["steps"] is None


def test_guidance_when_already_arrived(db):
    t = make_tourist(db, lat=26.1445, lng=91.7362,
                     itinerary=[{"name": "Here", "lat": 26.1445, "lng": 91.7362}])
    result = get_navigation_guidance(t)
    assert result["arrived"] is True
    assert "arrived" in result["instruction"].lower()


def test_guidance_skips_unplaced_waypoints(db):
    # An unplaced (no lat/lng) destination shouldn't be picked as "next" --
    # only real, geocoded stops are ever guided toward.
    t = make_tourist(db, lat=26.1445, lng=91.7362, itinerary=[
        {"name": "Somewhere unresolved"},
        {"name": "Kamakhya Temple", "lat": 26.1664, "lng": 91.7050},
    ])
    result = get_navigation_guidance(t)
    assert result["destination_name"] == "Kamakhya Temple"


def test_guidance_handles_malformed_itinerary_json_gracefully(db):
    # Tourist.itinerary is NOT NULL but nothing stops it holding garbage
    # (e.g. a partial write) -- must degrade to "no destination", not crash.
    t = make_tourist(db, itinerary=[])
    t.itinerary = "not valid json"
    db.commit()
    result = get_navigation_guidance(t)
    assert result == {"has_destination": False}
