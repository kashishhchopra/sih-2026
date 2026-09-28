"""Schemas for translation (app/api/translate.py)."""
from pydantic import BaseModel, Field


class TranslatePhraseRequest(BaseModel):
    phrase_id: str = Field(..., max_length=60)
    target_lang: str = Field(..., max_length=10)


class TranslateTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    target_lang: str = Field(..., max_length=10)
    source_lang: str | None = Field(None, max_length=10)


class TranslateGuidePhraseRequest(BaseModel):
    category: str = Field(..., max_length=60)
    phrase_id: str = Field(..., max_length=60)
    target_lang: str = Field(..., max_length=10)
