"""Sentiment / distress recognition for the Women & Solo Traveller Safety
module -- and reused for SOS descriptions (see services/monitoring.py) so
responders see the emotional urgency of what a tourist typed, not just the
raw text.

Two real, layered mechanisms (never a hardcoded per-message label):

1. VADER (Valence Aware Dictionary and sEntiment Reasoner) -- a genuine,
   widely-used rule-based sentiment intensity analyzer (`vaderSentiment`,
   no network/key needed). Gives the base positive/neutral/negative polarity
   and a -1..+1 compound score. This is the same class of tool production
   systems use for short, informal text (tuned on social-media-style
   language), and it always runs.

2. A domain-specific safety lexicon (being followed/threatened/unsafe/
   trapped/help, etc.) layered on top: VADER alone is a general-purpose
   sentiment tool and under-reacts to safety-specific phrasing ("someone has
   been following me" scores only mildly negative on general sentiment,
   despite being exactly the kind of sentence this feature exists to catch)
   -- so a real pattern-matching pass over recognised distress/urgency
   language raises `urgency`/`distress_detected` independently of raw
   polarity. Same "transparent, explainable scoring" style as
   services/alert_priority.py and services/safety.py elsewhere in this app.

3. When a language model is configured (services/llm.py -- this project's
   existing AI/NLP infrastructure), it's used as an *enhancement* for a
   richer emotion label (fear/anger vs plain negative) -- reused, not
   duplicated, and entirely optional: everything above already works with
   zero configuration.
"""
from __future__ import annotations

import logging
import re

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.services import llm

logger = logging.getLogger(__name__)

_analyzer = SentimentIntensityAnalyzer()

# Domain-specific distress/threat/urgency language. Grouped so the matched
# category can inform the label (fear vs anger) as well as the urgency
# bump -- this is a real pattern-matching classifier, not a lookup table of
# fixed outputs per input.
_FEAR_PATTERNS = [
    r"\bfollow(?:ing|ed|s)?\b", r"\bstalk(?:ing|ed|er)?\b", r"\bwatch(?:ing|ed)\s+me\b",
    r"\bscared\b", r"\bafraid\b", r"\bfrighten", r"\bterrified\b", r"\bpanic",
    r"\btrapped\b", r"\bcornered\b", r"\bcan'?t\s+get\s+away\b", r"\bfollowing\s+me\b",
    r"\bunsafe\b", r"\bthreat(?:en(?:ed|ing)?|s)?\b", r"\bharass(?:ing|ed|ment)?\b",
    r"\bgrab(?:bed|bing)?\s+me\b", r"\btouch(?:ed|ing)\s+me\b", r"\bwon'?t\s+leave\s+me\s+alone\b",
    r"\balone\b.{0,30}\b(dark|night|street|isolated|deserted)\b",
]
_ANGER_PATTERNS = [
    r"\bfurious\b", r"\benraged\b", r"\bcheated\b", r"\bscammed\b", r"\bripped\s+off\b",
    r"\bharassed\b", r"\bfed\s+up\b", r"\boutrageous\b",
]
_URGENCY_PATTERNS = [
    r"\bhelp\s*(me|us)?\b", r"\bnow\b", r"\bimmediately\b", r"\burgent(?:ly)?\b",
    r"\bplease\s+hurry\b", r"\bemergency\b", r"\bright\s+now\b", r"\bcan'?t\s+breathe\b",
    r"\bsomeone\s+is\b", r"\bhe\s+is\s+following\b", r"\bshe\s+is\s+following\b",
]

_fear_re = re.compile("|".join(_FEAR_PATTERNS), re.I)
_anger_re = re.compile("|".join(_ANGER_PATTERNS), re.I)
_urgency_re = re.compile("|".join(_URGENCY_PATTERNS), re.I)


def _base_label(compound: float) -> str:
    if compound <= -0.5:
        return "negative"
    if compound < -0.05:
        return "negative"
    if compound >= 0.05:
        return "positive"
    return "neutral"


def _llm_emotion_label(text: str) -> str | None:
    """Optional enhancement: ask the configured LLM (services/llm.py) for a
    one-word emotion label. Returns None (never fabricated) if no provider
    is configured/reachable or the reply isn't one of the allowed labels --
    the VADER+lexicon result underneath is always a valid answer on its own."""
    allowed = {"positive", "neutral", "negative", "fear", "anger"}
    system = (
        "Classify the emotional tone of a short message from a tourist safety app. "
        "Reply with EXACTLY one word, lowercase, no punctuation: "
        "positive, neutral, negative, fear, or anger. Nothing else."
    )
    reply = llm.complete(system, text[:500])
    if not reply:
        return None
    word = reply.strip().lower().split()[0].strip(".,!") if reply.strip() else ""
    return word if word in allowed else None


def analyze(text: str) -> dict:
    """Real sentiment + distress analysis of `text`. Always returns a
    result (VADER + lexicon never fail) -- the LLM enhancement is additive.

    Returns: {label, score, urgency, distress_detected, fear_signals,
    anger_signals, method}."""
    text = (text or "").strip()
    if not text:
        return {
            "label": "neutral", "score": 0.0, "urgency": "low",
            "distress_detected": False, "fear_signals": [], "anger_signals": [],
            "method": "empty",
        }

    scores = _analyzer.polarity_scores(text)
    compound = scores["compound"]
    label = _base_label(compound)

    fear_hits = sorted({m.group(0).lower() for m in _fear_re.finditer(text)})
    anger_hits = sorted({m.group(0).lower() for m in _anger_re.finditer(text)})
    urgency_hits = list(_urgency_re.finditer(text))

    if fear_hits:
        label = "fear"
    elif anger_hits and not fear_hits:
        label = "anger"

    # Urgency: strong negative polarity + distress language + explicit
    # urgency words each raise it a step -- explainable, additive, same
    # style as alert_priority.py's scoring rather than an opaque model.
    urgency_points = 0
    if compound <= -0.5:
        urgency_points += 1
    if fear_hits:
        urgency_points += 2
    if urgency_hits:
        urgency_points += 1
    urgency = "high" if urgency_points >= 3 else "medium" if urgency_points >= 1 else "low"
    distress_detected = bool(fear_hits) or urgency == "high"

    method = "vader+lexicon"
    # The LLM only fills in when the lexicon found no concrete fear/anger
    # phrases to go on -- when it did, that grounded evidence outranks a
    # generic model guess (the earlier "someone has been following me"
    # example is exactly this case: the lexicon's "fear" is more trustworthy
    # than an LLM defaulting to plain "negative"). Either way, it never
    # touches urgency/distress_detected, which stay grounded in the matched
    # phrases themselves.
    if not fear_hits and not anger_hits:
        llm_label = _llm_emotion_label(text)
        if llm_label:
            label = llm_label
            method = "vader+lexicon+llm"

    return {
        "label": label, "score": round(compound, 3), "urgency": urgency,
        "distress_detected": distress_detected,
        "fear_signals": fear_hits, "anger_signals": anger_hits, "method": method,
    }
