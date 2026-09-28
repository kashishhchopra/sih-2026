"""Real-data calibration for Zone.crime_index.

No state/UT-wise "crime against foreigners" dataset is available without a
data.gov.in API key (not obtainable in this environment) -- see
app/ml/etl/build_crime_index.py for the source and why. What IS real and
committed is the national, year-by-year series in
app/data/reference/ncrb_crime_against_foreigners.json (NCRB Chapter 13A,
2014-2021).

Rather than pretend to a per-state number this project doesn't have, this
module uses that real national series as a calibration ANCHOR: a defensible,
real-data-derived baseline "national crime pressure" index, which zones are
then differentiated against by their existing categorical risk tier
(low/medium/high/restricted -- a judgment already made when a zone is
created, e.g. "riverbank, entry prohibited after dusk"). The previous values
(15/40/70/85) were arbitrary; these are anchored to a real number, honestly
documented as national-level, not zone-specific.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "ncrb_crime_against_foreigners.json"

# A designed ceiling for the 0-100 scale, NOT itself an NCRB figure: the
# observed pre-COVID rate never exceeded ~6.33 per lakh FTA (2014), so 12.0
# leaves headroom for the index to move without immediately clipping at the
# historical maximum. Keeping this ceiling steady is what makes the index
# comparable across ETL re-runs as new NCRB years are added.
_BASELINE_SCALE_MAX = 12.0

# Multiplies the real national baseline to differentiate zones by their
# existing categorical risk tier. Ordering (not the exact values) is what
# the safety-score model actually relies on via zone_risk/crime_index.
_TIER_MULTIPLIER = {"low": 0.4, "medium": 0.8, "high": 1.3, "restricted": 1.6}
_DEFAULT_TIER_MULTIPLIER = 0.8  # unknown/custom tier -> treat as medium


@lru_cache(maxsize=1)
def load_ncrb_series() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def national_baseline_crime_index() -> float:
    """0-100 index derived from the mean pre-COVID (non-anomalous) NCRB
    crime rate against foreigners. COVID years are excluded because their
    rate spike reflects a collapsed foreign-tourist-arrival denominator, not
    a real change in risk to tourists -- see the dataset's `_meta.note`."""
    series = load_ncrb_series()["series"]
    clean = [row["crime_rate_per_lakh_fta"] for row in series if not row.get("covid_anomalous")]
    if not clean:
        return 30.0  # defensive fallback; the committed dataset always has clean years
    mean_rate = sum(clean) / len(clean)
    return round(min(100.0, max(0.0, (mean_rate / _BASELINE_SCALE_MAX) * 100.0)), 2)


def calibrate_zone_crime_index(risk_level: str) -> float:
    """crime_index for a zone of this risk_level, anchored to the real
    national baseline above rather than an arbitrary hand-picked number."""
    multiplier = _TIER_MULTIPLIER.get(risk_level, _DEFAULT_TIER_MULTIPLIER)
    return round(min(100.0, national_baseline_crime_index() * multiplier), 2)
