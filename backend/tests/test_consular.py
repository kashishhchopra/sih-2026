"""Embassy directory & country guidance (app/services/consular.py)."""
from app.services import consular


def test_normalize_nationality_from_demonym():
    assert consular.normalize_nationality("Japanese") == "JP"
    assert consular.normalize_nationality("British") == "GB"
    assert consular.normalize_nationality("Italian") == "IT"


def test_normalize_nationality_from_country_name():
    assert consular.normalize_nationality("Japan") == "JP"
    assert consular.normalize_nationality("Germany") == "DE"


def test_normalize_nationality_from_iso_code_case_insensitive():
    assert consular.normalize_nationality("jp") == "JP"
    assert consular.normalize_nationality("US") == "US"


def test_normalize_nationality_unrecognised_returns_none():
    assert consular.normalize_nationality("Atlantean") is None
    assert consular.normalize_nationality("") is None
    assert consular.normalize_nationality(None) is None


def test_normalize_nationality_unrecognised_two_letter_code_returns_none():
    assert consular.normalize_nationality("ZZ") is None


def test_missions_for_returns_empty_for_no_country():
    assert consular.missions_for(None) == []


def test_missions_for_returns_matches_for_a_known_country():
    missions = consular.missions_for("JP")
    assert len(missions) >= 1
    assert all(m["country_code"] == "JP" for m in missions)


def test_missions_for_sorts_by_distance_when_position_given():
    # Delhi coordinates -- nearer to the New Delhi mission than any other.
    missions = consular.missions_for("JP", lat=28.60, lng=77.19)
    assert missions[0]["city"] == "New Delhi"
    assert "distance_km" in missions[0]
    distances = [m["distance_km"] for m in missions]
    assert distances == sorted(distances)


def test_missions_for_unknown_country_returns_empty():
    assert consular.missions_for("ZZ") == []


def test_guidance_for_known_country_includes_its_helpline_language():
    g = consular.guidance_for("JP")
    assert g["helpline_language"] == "Japanese"
    assert "common_scams" in g  # inherited from _default


def test_guidance_for_unknown_or_missing_country_returns_default():
    default = consular.guidance_for(None)
    assert default["helpline_language"] == "English"
    assert consular.guidance_for("ZZ") == default
