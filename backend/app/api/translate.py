"""Translation: the curated emergency phrasebook (always available, no
external API needed) and free-text translation (real when
GOOGLE_TRANSLATE_API_KEY is set, otherwise a clearly-marked demo passthrough).
See services/translation.py.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.translate import (
    TranslateGuidePhraseRequest,
    TranslatePhraseRequest,
    TranslateTextRequest,
)
from app.services import translation

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
def translate_guide_phrase(payload: TranslateGuidePhraseRequest, _: User = Depends(get_current_user)):
    return translation.translate_guide_phrase(payload.category, payload.phrase_id, payload.target_lang)
