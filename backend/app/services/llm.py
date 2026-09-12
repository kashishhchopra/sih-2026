"""Open-ended language-model backend for the assistant.

The intent router in services/copilot.py answers safety-critical questions
from real database queries -- a tourist asking "where is the nearest
hospital?" must get an actual row with an actual distance, never a
plausible-sounding invention. That router is deliberately narrow, so
anything outside it used to hit a dead end.

This module is what handles everything else: a general question gets a real
language-model answer, grounded in the tourist's own live context (where
they are, what their itinerary says, how safe the area is).

Providers, tried in order unless `LLM_PROVIDER` names one explicitly:
  * ollama    -- a local model (default; free, no API key, no data leaves
                 the machine). Just needs `ollama serve` running.
  * openai    -- when OPENAI_API_KEY is set.
  * anthropic -- when ANTHROPIC_API_KEY is set.

If none is reachable, `complete()` returns None and the caller falls back
to its own deterministic reply -- the app never breaks, it just loses the
open-ended answers.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _ollama_complete(system: str, user: str) -> str | None:
    try:
        resp = httpx.post(
            f"{settings.OLLAMA_URL.rstrip('/')}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "num_predict": settings.LLM_MAX_TOKENS,
                    "temperature": settings.LLM_TEMPERATURE,
                },
            },
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        content = (resp.json().get("message") or {}).get("content", "").strip()
        return content or None
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning("Ollama completion failed: %s", e)
        return None


def _openai_complete(system: str, user: str) -> str | None:
    try:
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": settings.OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": settings.LLM_MAX_TOKENS,
                "temperature": settings.LLM_TEMPERATURE,
            },
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return (resp.json()["choices"][0]["message"]["content"] or "").strip() or None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        logger.warning("OpenAI completion failed: %s", e)
        return None


def _anthropic_complete(system: str, user: str) -> str | None:
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.ANTHROPIC_MODEL,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": settings.LLM_MAX_TOKENS,
                "temperature": settings.LLM_TEMPERATURE,
            },
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return (resp.json()["content"][0]["text"] or "").strip() or None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        logger.warning("Anthropic completion failed: %s", e)
        return None


def _ollama_reachable() -> bool:
    try:
        httpx.get(f"{settings.OLLAMA_URL.rstrip('/')}/api/tags", timeout=1.5).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


def active_provider() -> str | None:
    """Which backend would answer right now, or None if the assistant has no
    open-ended capability available. Cheap enough to call per request except
    for the ollama reachability probe, which is only hit in "auto" mode."""
    if not settings.LLM_ENABLED or settings.is_test:
        return None

    choice = (settings.LLM_PROVIDER or "auto").lower()
    if choice == "none":
        return None
    if choice == "openai":
        return "openai" if settings.OPENAI_API_KEY else None
    if choice == "anthropic":
        return "anthropic" if settings.ANTHROPIC_API_KEY else None
    if choice == "ollama":
        return "ollama"

    # auto: prefer a configured cloud key (better answers), else the local
    # model, else nothing.
    if settings.ANTHROPIC_API_KEY:
        return "anthropic"
    if settings.OPENAI_API_KEY:
        return "openai"
    if _ollama_reachable():
        return "ollama"
    return None


def complete(system: str, user: str) -> str | None:
    """One open-ended completion. Returns None (never raises, never a
    placeholder string) when no provider is available or the call fails, so
    callers can fall back to their own deterministic answer."""
    provider = active_provider()
    if provider is None:
        return None
    if provider == "anthropic":
        return _anthropic_complete(system, user)
    if provider == "openai":
        return _openai_complete(system, user)
    return _ollama_complete(system, user)
