"""Translation: the curated emergency phrasebook (always available, no
external API needed) and free-text translation (real when
GOOGLE_TRANSLATE_API_KEY is set, otherwise a clearly-marked demo passthrough).
See services/translation.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.translate import (
    TranslateGuidePhraseRequest,
    TranslatePhraseRequest,
    TranslateTextRequest,
)
from app.services import place_info, translation

router = APIRouter(prefix="/translate", tags=["translate"])


@router.get("/languages")
def list_languages(_: User = Depends(get_current_user)):
    return translation.SUPPORTED_LANGUAGES


@router.get("/phrases")
def list_phrases(_: User = Depends(get_current_user)):
    """Every curated emergency phrase id, for the frontend to render as
    quick-translate buttons."""
    return translation.list_phrase_ids()


@router.post("/phrase")
def translate_phrase(payload: TranslatePhraseRequest, _: User = Depends(get_current_user)):
    return translation.translate_phrase(payload.phrase_id, payload.target_lang)


@router.post("/text")
def translate_text(payload: TranslateTextRequest, _: User = Depends(get_current_user)):
    return translation.translate_text(payload.text, payload.target_lang, payload.source_lang)


# ---- Multilingual Guide: everyday phrasebook, grouped by category ----

@router.get("/guide/categories")
def list_guide_categories(_: User = Depends(get_current_user)):
    return translation.list_guide_categories()


@router.get("/guide/{category}")
def list_guide_phrases(category: str, _: User = Depends(get_current_user)):
    return translation.list_guide_phrase_ids(category)


@router.post("/guide/phrase")
def translate_guide_phrase(
    payload: TranslateGuidePhraseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Most phrases stay a plain curated phrase (see services/translation.py)
    -- courtesy/negotiation phrases like "I am vegetarian" or "Can you lower
    the price?" are things to SAY, not queries. A handful of specific
    location-QUERY phrases instead answer with real, live data about the
    tourist's actual current location (see services/place_info.py): their
    zone/safety status, nearest emergency services, and nearby food/shops.
    """
    tourist = db.get(Tourist, user.tourist_id) if user.tourist_id else None
    lang = payload.target_lang
    category, phrase_id = payload.category, payload.phrase_id

    if tourist and category == "directions" and phrase_id == "where_is_this":
        return place_info.describe_current_zone(db, tourist, lang)
    if tourist and category == "directions" and phrase_id == "how_far":
        return place_info.describe_nearest_help(db, tourist, lang)
    if tourist and category == "food" and phrase_id == "recommend_local_food":
        if tourist.last_lat is not None:
            return place_info.describe_nearby_food(db, tourist.last_lat, tourist.last_lng, lang)
        return place_info.no_location_message(lang)
    if tourist and category == "shopping" and phrase_id == "how_much":
        if tourist.last_lat is not None:
            return place_info.describe_nearby_shopping(tourist.last_lat, tourist.last_lng, lang)
        return place_info.no_location_message(lang)

    return translation.translate_guide_phrase(category, phrase_id, lang)
