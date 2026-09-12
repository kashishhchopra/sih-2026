"""Real-data crime index calibration (app/services/crime_index.py)."""
from app.services import crime_index


def test_load_ncrb_series_has_the_expected_years():
    data = crime_index.load_ncrb_series()
    years = [row["year"] for row in data["series"]]
    assert years == list(range(2014, 2022))


def test_national_baseline_is_a_positive_number_within_0_100():
    baseline = crime_index.national_baseline_crime_index()
    assert 0.0 < baseline < 100.0


def test_national_baseline_excludes_covid_anomalous_years():
    """2020/2021 have a much higher raw rate (collapsed FTA denominator);
    the baseline must not be skewed upward by including them."""
    data = crime_index.load_ncrb_series()
    clean_rates = [r["crime_rate_per_lakh_fta"] for r in data["series"] if not r.get("covid_anomalous")]
    all_rates = [r["crime_rate_per_lakh_fta"] for r in data["series"]]
    clean_mean = sum(clean_rates) / len(clean_rates)
    all_mean = sum(all_rates) / len(all_rates)
    assert clean_mean < all_mean  # sanity: COVID years really do pull the mean up

    baseline = crime_index.national_baseline_crime_index()
    expected = round(min(100.0, (clean_mean / crime_index._BASELINE_SCALE_MAX) * 100.0), 2)
    assert baseline == expected


def test_tier_ordering_is_monotonic():
    """restricted zones must always calibrate to a higher index than high,
    which must be higher than medium, then low -- the safety model depends
    on this ordering via zone_risk/crime_index, not the exact numbers."""
    low = crime_index.calibrate_zone_crime_index("low")
    medium = crime_index.calibrate_zone_crime_index("medium")
    high = crime_index.calibrate_zone_crime_index("high")
    restricted = crime_index.calibrate_zone_crime_index("restricted")
    assert low < medium < high < restricted


def test_unknown_tier_falls_back_to_medium_multiplier():
    unknown = crime_index.calibrate_zone_crime_index("not-a-real-tier")
    medium = crime_index.calibrate_zone_crime_index("medium")
    assert unknown == medium


def test_calibrated_values_are_clipped_to_0_100():
    for tier in ["low", "medium", "high", "restricted"]:
        value = crime_index.calibrate_zone_crime_index(tier)
        assert 0.0 <= value <= 100.0
