"""Embassy/consulate directory and country-specific guidance for foreign
tourists -- committed reference data (app/data/reference/embassies.json,
country_guidance.json), not a live feed: no clean machine-readable API for
either exists, and this is exactly the kind of small, slow-changing data
that should keep working with zero network access (see safety_card.py,
which is what surfaces this offline).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from app.services.geo import haversine_m

_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "reference"

# Tourist.nationality is free-text as typed at registration ("Japanese",
# "Japan", "JP") -- not one canonical form. This maps common demonyms and
# country names to ISO 3166-1 alpha-2, covering the nationalities in this
# app's own seed data plus the missions actually in embassies.json.
_DEMONYM_TO_CODE = {
    "american": "US", "united states": "US", "usa": "US", "us": "US",
    "british": "GB", "united kingdom": "GB", "uk": "GB", "britain": "GB",
    "japanese": "JP", "japan": "JP",
    "korean": "KR", "south korean": "KR", "south korea": "KR", "korea": "KR",
    "chinese": "CN", "china": "CN",
    "french": "FR", "france": "FR",
    "german": "DE", "germany": "DE",
    "spanish": "ES", "spain": "ES",
    "russian": "RU", "russia": "RU",
    "saudi": "SA", "saudi arabian": "SA", "saudi arabia": "SA",
    "emirati": "AE", "uae": "AE", "united arab emirates": "AE",
    "portuguese": "PT", "portugal": "PT",
    "italian": "IT", "italy": "IT",
    "australian": "AU", "australia": "AU",
    "canadian": "CA", "canada": "CA",
    "dutch": "NL", "netherlands": "NL",
    "singaporean": "SG", "singapore": "SG",
    "thai": "TH", "thailand": "TH",
    "israeli": "IL", "israel": "IL",
    "bangladeshi": "BD", "bangladesh": "BD",
    "nepali": "NP", "nepalese": "NP", "nepal": "NP",
    "indian": "IN", "india": "IN",
}


@lru_cache(maxsize=1)
def _embassies() -> list[dict]:
    with open(_DATA_DIR / "embassies.json", encoding="utf-8") as f:
        return json.load(f)["missions"]


@lru_cache(maxsize=1)
def _guidance() -> dict:
    with open(_DATA_DIR / "country_guidance.json", encoding="utf-8") as f:
        return json.load(f)


def normalize_nationality(value: str | None) -> str | None:
    """Best-effort free-text nationality/country -> ISO 3166-1 alpha-2.
    Returns None (not "IN") for anything unrecognised -- callers treat that
    as "no consular info to show", which is also correct for an already-
    2-letter unrecognised code."""
    if not value:
        return None
    cleaned = value.strip()
    if re.fullmatch(r"[A-Za-z]{2}", cleaned) and cleaned.upper() in {
        m["country_code"] for m in _embassies()
    } | {"IN"}:
        return cleaned.upper()
    return _DEMONYM_TO_CODE.get(cleaned.lower())


def missions_for(country_code: str | None, lat: float | None = None,
                 lng: float | None = None) -> list[dict]:
    """Missions for a country, nearest first when a position is given."""
    if not country_code:
        return []
    matches = [m for m in _embassies() if m["country_code"] == country_code.upper()]
    if lat is None or lng is None:
        return matches
    with_distance = [
        {**m, "distance_km": round(haversine_m(lat, lng, m["lat"], m["lng"]) / 1000, 1)}
        for m in matches
    ]
    return sorted(with_distance, key=lambda m: m["distance_km"])


def guidance_for(country_code: str | None) -> dict:
    data = _guidance()
    default = data["_default"]
    if not country_code:
        return default
    override = data["countries"].get(country_code.upper(), {})
    return {**default, **override}
