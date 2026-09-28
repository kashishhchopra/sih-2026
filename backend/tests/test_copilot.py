"""AI Safety Copilot (services/copilot.py, /copilot/ask, /tourists/{id}/copilot/ask)."""
from app.models.alert import Alert
from tests.conftest import make_tourist, make_unit, make_zone


def test_operator_why_flagged_uses_real_score(client, admin_headers, db):
    t = make_tourist(db)
    r = client.post("/api/copilot/ask", headers=admin_headers,
                    json={"question": f"why was tourist {t.id} flagged?"})
    assert r.status_code == 200
    body = r.json()
    assert body["handled"] is True
    assert t.full_name in body["answer"]


def test_operator_why_flagged_unknown_tourist(client, admin_headers):
    r = client.post("/api/copilot/ask", headers=admin_headers,
                    json={"question": "why was tourist 99999 flagged?"})
    assert "couldn't find" in r.json()["answer"]


def test_operator_at_risk_list(client, admin_headers, db):
    make_tourist(db, name="Low Score")
    r = client.post("/api/copilot/ask", headers=admin_headers,
                    json={"question": "which tourists are at risk right now?"})
    assert r.status_code == 200
    assert r.json()["handled"] is True


def test_operator_alert_summary(client, admin_headers, db):
    t = make_tourist(db)
    db.add(Alert(tourist_id=t.id, type="sos", severity="critical", message="x"))
    db.commit()
    r = client.post("/api/copilot/ask", headers=admin_headers,
                    json={"question": "how many active alerts are there?"})
    assert "1" in r.json()["answer"]


def test_operator_dispatch_query(client, admin_headers, db):
    make_unit(db, name="Alpha", lat=26.1450, lng=91.7365)
    t = make_tourist(db, lat=26.1445, lng=91.7362)
    r = client.post("/api/copilot/ask", headers=admin_headers,
                    json={"question": f"nearest unit to tourist {t.id}"})
    assert "Alpha" in r.json()["answer"]


def test_operator_fallback_help_menu(client, admin_headers):
    r = client.post("/api/copilot/ask", headers=admin_headers, json={"question": "banana"})
    assert r.json()["handled"] is False
    assert "I can answer" in r.json()["answer"]


def test_operator_copilot_forbidden_for_tourist(client, tourist_headers):
    r = client.post("/api/copilot/ask", headers=tourist_headers, json={"question": "hi"})
    assert r.status_code == 403


# ---------------------------------------------------------------- tourist side
def test_tourist_nearest_hospital(client, tourist_headers, tourist_user, db):
    # tourist_user's Tourist row defaults to (26.1445, 91.7362) -- see
    # tests/conftest.py:make_tourist().
    make_unit(db, name="City Hospital", unit_type="ambulance", lat=26.145, lng=91.737)
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "where is the nearest hospital?"})
    assert r.status_code == 200
    assert "City Hospital" in r.json()["answer"]


def test_tourist_area_safety(client, tourist_headers, tourist_user, db):
    make_zone(db, risk="restricted", lat=26.1445, lng=91.7362, d=0.01)
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "is this area safe?"})
    assert r.status_code == 200
    assert "restricted" in r.json()["answer"] or "risk" in r.json()["answer"]


def test_tourist_advice(client, tourist_headers, tourist_user):
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "what should I do now?"})
    assert r.status_code == 200
    assert r.json()["handled"] is True


def test_tourist_embassy_lookup_for_foreign_national(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist

    t = db.get(Tourist, tourist_user.tourist_id)
    t.nationality = "Japanese"
    db.commit()

    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "where is my embassy?"})
    assert r.status_code == 200
    assert "Japan" in r.json()["answer"]


def test_tourist_embassy_lookup_for_indian_national_is_not_applicable(client, tourist_headers, tourist_user):
    # tourist_user's Tourist row defaults to nationality="Indian".
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "where is my embassy?"})
    assert r.status_code == 200
    assert "foreign tourists" in r.json()["answer"]


def test_tourist_copilot_forbidden_for_other_tourist(client, tourist_headers, db):
    other = make_tourist(db, name="Not Me")
    r = client.post(f"/api/tourists/{other.id}/copilot/ask", headers=tourist_headers,
                    json={"question": "hi"})
    assert r.status_code == 403


# ---------------------------------------------------------------- itinerary-aware
def _set_itinerary(db, tourist, stops):
    import json
    tourist.itinerary = json.dumps(stops)
    db.commit()


def test_tourist_next_destination(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    _set_itinerary(db, t, [{"name": "Agra", "lat": 27.1767, "lng": 78.0081}])

    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "what's my next destination?"})
    assert r.status_code == 200
    assert "Agra" in r.json()["answer"]


def test_tourist_next_destination_no_itinerary(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    _set_itinerary(db, t, [])  # make_tourist seeds a default "Start" stop -- clear it

    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "where am I going next?"})
    assert r.status_code == 200
    assert "upload" in r.json()["answer"].lower()


def test_tourist_show_itinerary(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    _set_itinerary(db, t, [
        {"name": "Delhi", "lat": 28.6139, "lng": 77.2090},
        {"name": "Agra", "lat": 27.1767, "lng": 78.0081},
    ])
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "show my itinerary"})
    assert r.status_code == 200
    assert "Delhi" in r.json()["answer"] and "Agra" in r.json()["answer"]


def test_tourist_on_route_when_following_plan(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    _set_itinerary(db, t, [{"name": "Nearby Stop", "lat": t.last_lat, "lng": t.last_lng}])

    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "am I on the correct route?"})
    assert r.status_code == 200
    assert "on your planned route" in r.json()["answer"]


def test_tourist_on_route_flags_significant_deviation(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    # itinerary stop far from the tourist's current (last_lat/last_lng) position
    _set_itinerary(db, t, [{"name": "Faraway City", "lat": 28.6139, "lng": 77.2090}])

    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "am I on track?"})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "navigation" in answer.lower() or "km" in answer


def test_tourist_nearest_transport(client, tourist_headers, tourist_user, db):
    from tests.conftest import make_poi
    make_poi(db, name="City Bus Stop", category="bus_stop",
            lat=26.1450, lng=91.7370)
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "find transport near me"})
    assert r.status_code == 200
    assert "City Bus Stop" in r.json()["answer"]


def test_tourist_nearest_pharmacy(client, tourist_headers, tourist_user, db):
    from tests.conftest import make_poi
    make_poi(db, name="City Pharmacy", category="pharmacy", lat=26.1450, lng=91.7370, phone="100")
    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "find a pharmacy"})
    assert r.status_code == 200
    assert "City Pharmacy" in r.json()["answer"]


def test_tourist_emergency_call_never_triggers_real_sos(client, tourist_headers, tourist_user, db):
    from app.models.incident import Incident
    before = db.query(Incident).count()

    r = client.post(f"/api/tourists/{tourist_user.tourist_id}/copilot/ask", headers=tourist_headers,
                    json={"question": "call emergency services"})
    assert r.status_code == 200
    assert "SOS" in r.json()["answer"]
    assert db.query(Incident).count() == before  # no incident silently created


# ---- complete voice-command coverage ----
def _ask(client, headers, tourist_id, question):
    r = client.post(f"/api/tourists/{tourist_id}/copilot/ask", headers=headers,
                    json={"question": question})
    assert r.status_code == 200
    return r.json()["answer"]


def test_tourist_find_a_cab_routes_to_taxi_stand(client, tourist_headers, tourist_user, db):
    from tests.conftest import make_poi
    make_poi(db, name="Paltan Bazaar Taxi Stand", category="taxi_stand", lat=26.1450, lng=91.7370)
    answer = _ask(client, tourist_headers, tourist_user.tourist_id, "find a cab")
    assert "Paltan Bazaar Taxi Stand" in answer


def test_tourist_take_me_to_my_hotel(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    t.hotel = "Delhi"  # resolvable via the offline gazetteer in tests
    db.commit()
    answer = _ask(client, tourist_headers, tourist_user.tourist_id, "take me to my hotel")
    assert "Delhi" in answer
    assert "km" in answer


def test_tourist_hotel_without_one_on_file_says_so(client, tourist_headers, tourist_user, db):
    from app.models.tourist import Tourist
    t = db.get(Tourist, tourist_user.tourist_id)
    t.hotel = None
    db.commit()
    answer = _ask(client, tourist_headers, tourist_user.tourist_id, "take me to my hotel")
    assert "don't have a hotel" in answer.lower()


def test_tourist_emergency_procedure_guidance(client, tourist_headers, tourist_user):
    answer = _ask(client, tourist_headers, tourist_user.tourist_id,
                  "what should I do in an emergency?")
    assert "SOS" in answer and "112" in answer


def test_tourist_translate_asks_what_and_which_language(client, tourist_headers, tourist_user):
    answer = _ask(client, tourist_headers, tourist_user.tourist_id, "translate this")
    assert "Hindi" in answer  # lists the supported languages


def test_tourist_translate_extracts_phrase_and_language_from_free_speech(
        client, tourist_headers, tourist_user):
    # No live translation API key in tests -- it must say so rather than
    # inventing a translation.
    answer = _ask(client, tourist_headers, tourist_user.tourist_id,
                  "how do I say I need a doctor in Hindi")
    assert "Hindi" in answer
    assert "doctor" not in answer.lower() or "isn't configured" in answer


def test_unmatched_question_reflects_back_what_was_heard(client, tourist_headers, tourist_user):
    answer = _ask(client, tourist_headers, tourist_user.tourist_id,
                  "please book me a hot air balloon ride")
    assert "hot air balloon" in answer  # so a mis-heard voice command is obvious
    assert "nearest hospital" in answer


def test_public_copilot_requires_no_auth(client):
    # The whole point of this endpoint: reachable before login, from the
    # Login/Register screen's voice assistant.
    r = client.post("/api/copilot/public", json={"question": "how does this app work?"})
    assert r.status_code == 200
    body = r.json()
    assert "MUSAFIR" in body["answer"]


def test_public_copilot_never_touches_tourist_data(client, db):
    # No LLM configured in tests (settings.is_test), so this exercises the
    # honest fallback -- and proves the response can't contain another
    # tourist's data, because the handler never queries the database at all.
    t = make_tourist(db, name="Should Never Appear")
    r = client.post("/api/copilot/public", json={"question": "who is Should Never Appear?"})
    assert r.status_code == 200
    assert t.full_name not in r.json()["answer"]


def test_public_copilot_gives_real_emergency_numbers_via_fallback(client):
    # Even without an LLM configured (as in tests), the pre-login assistant
    # must still surface real emergency numbers -- a blind tourist asking
    # for emergency help shouldn't depend on an LLM being reachable.
    r = client.post("/api/copilot/public", json={"question": "what can this app do?"})
    assert r.status_code == 200
    answer = r.json()["answer"]
    assert "112" in answer and "1363" in answer


def test_public_copilot_empty_question(client):
    r = client.post("/api/copilot/public", json={"question": ""})
    assert r.status_code == 422  # min_length=1 on CopilotQuestion


def test_public_emergency_numbers_are_the_real_shared_constants(client):
    # The pre-login voice assistant speaks these; they must be the same
    # values the authenticated Safety Card serves, not a second copy that
    # could drift out of sync.
    from app.services.safety_card import EMERGENCY_NUMBERS

    r = client.get("/api/copilot/public/emergency-numbers")
    assert r.status_code == 200
    assert r.json() == EMERGENCY_NUMBERS
    assert r.json()["all_in_one"] == "112"


def test_public_emergency_numbers_need_no_auth(client):
    # No Authorization header at all -- reachable from the login screen.
    r = client.get("/api/copilot/public/emergency-numbers")
    assert r.status_code == 200
