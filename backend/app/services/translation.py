"""Translation service abstraction, backed by Google Cloud Translation when
`settings.GOOGLE_TRANSLATE_API_KEY` is set, and a small built-in emergency
phrasebook when it isn't -- same shape as services/maps.py and
services/weather.py: one narrow interface, a real backend when a key
exists, a deterministic and clearly-labelled fallback when it doesn't.

The phrasebook only ever covers a fixed, curated set of safety-critical
phrases (not arbitrary free text) -- translating open-ended text without a
real NMT backend would mean fabricating a translation, which this project's
own rules explicitly forbid. Free text with no key configured is returned
unmodified, `demo: True`, with a note saying so.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "en": "English", "hi": "Hindi", "fr": "French", "de": "German",
    "es": "Spanish", "ja": "Japanese", "zh": "Chinese", "ko": "Korean",
    "ar": "Arabic",
}

# Curated safety-critical phrases, keyed by a stable phrase id -- real,
# reviewed translations (not machine-generated at request time), used only
# when no live translation API is configured. Extend this table rather than
# ever guessing a translation for an unlisted phrase.
_PHRASEBOOK: dict[str, dict[str, str]] = {
    "need_doctor": {
        "en": "I need a doctor. I am injured.",
        "hi": "मुझे डॉक्टर चाहिए। मैं घायल हूँ।",
        "fr": "J'ai besoin d'un médecin. Je suis blessé(e).",
        "de": "Ich brauche einen Arzt. Ich bin verletzt.",
        "es": "Necesito un médico. Estoy herido/a.",
        "ja": "医者が必要です。怪我をしています。",
        "zh": "我需要医生。我受伤了。",
        "ko": "의사가 필요해요. 다쳤어요.",
        "ar": "أحتاج إلى طبيب. أنا مصاب.",
    },
    "call_police": {
        "en": "Please call the police.",
        "hi": "कृपया पुलिस को बुलाएँ।",
        "fr": "Veuillez appeler la police.",
        "de": "Bitte rufen Sie die Polizei.",
        "es": "Por favor llame a la policía.",
        "ja": "警察を呼んでください。",
        "zh": "请报警。",
        "ko": "경찰을 불러주세요.",
        "ar": "من فضلك اتصل بالشرطة.",
    },
    "lost": {
        "en": "I am lost. Can you help me?",
        "hi": "मैं रास्ता भटक गया/गई हूँ। क्या आप मेरी मदद कर सकते हैं?",
        "fr": "Je suis perdu(e). Pouvez-vous m'aider ?",
        "de": "Ich habe mich verirrt. Können Sie mir helfen?",
        "es": "Estoy perdido/a. ¿Puede ayudarme?",
        "ja": "道に迷いました。手伝ってもらえますか。",
        "zh": "我迷路了。你能帮帮我吗？",
        "ko": "길을 잃었어요. 도와주시겠어요?",
        "ar": "أنا تائه. هل يمكنك مساعدتي؟",
    },
    "need_hospital": {
        "en": "Where is the nearest hospital?",
        "hi": "सबसे नज़दीकी अस्पताल कहाँ है?",
        "fr": "Où est l'hôpital le plus proche ?",
        "de": "Wo ist das nächste Krankenhaus?",
        "es": "¿Dónde está el hospital más cercano?",
        "ja": "一番近い病院はどこですか。",
        "zh": "最近的医院在哪里？",
        "ko": "가장 가까운 병원이 어디예요?",
        "ar": "أين أقرب مستشفى؟",
    },
    "thank_you": {
        "en": "Thank you for your help.",
        "hi": "आपकी मदद के लिए धन्यवाद।",
        "fr": "Merci pour votre aide.",
        "de": "Danke für Ihre Hilfe.",
        "es": "Gracias por su ayuda.",
        "ja": "助けてくれてありがとうございます。",
        "zh": "谢谢你的帮助。",
        "ko": "도와주셔서 감사합니다.",
        "ar": "شكرا لمساعدتك.",
    },
}


# Multilingual Guide: everyday phrases beyond the safety-critical set above,
# grouped by category so the tourist app can render a phrasebook (greetings,
# directions, food, shopping, numbers) rather than only emergency lines.
# Same rule as _PHRASEBOOK: real, reviewed text only, never machine-generated
# at request time.
_GUIDE_PHRASEBOOK: dict[str, dict[str, dict[str, str]]] = {
    "greetings": {
        "hello": {
            "en": "Hello", "hi": "नमस्ते", "fr": "Bonjour", "de": "Hallo",
            "es": "Hola", "ja": "こんにちは", "zh": "你好", "ko": "안녕하세요", "ar": "مرحباً",
        },
        "goodbye": {
            "en": "Goodbye", "hi": "अलविदा", "fr": "Au revoir", "de": "Auf Wiedersehen",
            "es": "Adiós", "ja": "さようなら", "zh": "再见", "ko": "안녕히 가세요", "ar": "وداعاً",
        },
        "please": {
            "en": "Please", "hi": "कृपया", "fr": "S'il vous plaît", "de": "Bitte",
            "es": "Por favor", "ja": "お願いします", "zh": "请", "ko": "부탁합니다", "ar": "من فضلك",
        },
    },
    "directions": {
        "where_is_this": {
            "en": "Where is this place?", "hi": "यह जगह कहाँ है?", "fr": "Où est cet endroit ?",
            "de": "Wo ist dieser Ort?", "es": "¿Dónde está este lugar?", "ja": "この場所はどこですか。",
            "zh": "这个地方在哪里？", "ko": "이곳이 어디예요?", "ar": "أين هذا المكان؟",
        },
        "how_far": {
            "en": "How far is it from here?", "hi": "यहाँ से कितनी दूर है?",
            "fr": "C'est à quelle distance d'ici ?", "de": "Wie weit ist es von hier?",
            "es": "¿A qué distancia está de aquí?", "ja": "ここからどのくらい遠いですか。",
            "zh": "从这里有多远？", "ko": "여기서 얼마나 멀어요?", "ar": "كم تبعد من هنا؟",
        },
    },
    "food": {
        "recommend_local_food": {
            "en": "Can you recommend a local dish?", "hi": "क्या आप कोई स्थानीय व्यंजन सुझा सकते हैं?",
            "fr": "Pouvez-vous recommander un plat local ?", "de": "Können Sie ein lokales Gericht empfehlen?",
            "es": "¿Puede recomendar un plato local?", "ja": "地元の料理を勧めてもらえますか。",
            "zh": "你能推荐一道当地菜吗？", "ko": "현지 음식을 추천해 주시겠어요?", "ar": "هل يمكنك أن توصي بطبق محلي؟",
        },
        "vegetarian": {
            "en": "I am vegetarian.", "hi": "मैं शाकाहारी हूँ।", "fr": "Je suis végétarien(ne).",
            "de": "Ich bin Vegetarier(in).", "es": "Soy vegetariano/a.", "ja": "私はベジタリアンです。",
            "zh": "我吃素。", "ko": "저는 채식주의자예요.", "ar": "أنا نباتي.",
        },
    },
    "shopping": {
        "how_much": {
            "en": "How much does this cost?", "hi": "इसकी कीमत कितनी है?", "fr": "Combien ça coûte ?",
            "de": "Wie viel kostet das?", "es": "¿Cuánto cuesta esto?", "ja": "これはいくらですか。",
            "zh": "这个多少钱？", "ko": "이거 얼마예요?", "ar": "كم يكلف هذا؟",
        },
        "too_expensive": {
            "en": "That's too expensive.", "hi": "यह बहुत महँगा है।", "fr": "C'est trop cher.",
            "de": "Das ist zu teuer.", "es": "Eso es demasiado caro.", "ja": "それは高すぎます。",
            "zh": "太贵了。", "ko": "너무 비싸요.", "ar": "هذا غالٍ جداً.",
        },
    },
}


def list_guide_categories() -> list[str]:
    return sorted(_GUIDE_PHRASEBOOK.keys())


def list_guide_phrase_ids(category: str) -> list[str]:
    return sorted(_GUIDE_PHRASEBOOK.get(category, {}).keys())


def translate_guide_phrase(category: str, phrase_id: str, target_lang: str) -> dict:
    entry = _GUIDE_PHRASEBOOK.get(category, {}).get(phrase_id)
    if entry is None:
        return {"text": None, "demo": True, "error": f"Unknown guide phrase: {category}/{phrase_id}"}
    text = entry.get(target_lang, entry["en"])
    return {"text": text, "demo": False, "category": category, "phrase_id": phrase_id, "lang": target_lang}


def list_phrase_ids() -> list[str]:
    return sorted(_PHRASEBOOK.keys())


def translate_phrase(phrase_id: str, target_lang: str) -> dict:
    """Translate a known safety-critical phrase into `target_lang`. Always
    succeeds for a listed phrase/language pair (real, reviewed text) --
    this is the path emergency UI should use, since it never depends on a
    live API being reachable."""
    entry = _PHRASEBOOK.get(phrase_id)
    if entry is None:
        return {"text": None, "demo": True, "error": f"Unknown phrase: {phrase_id}"}
    text = entry.get(target_lang, entry["en"])
    return {"text": text, "demo": False, "phrase_id": phrase_id, "lang": target_lang}


def translate_text(text: str, target_lang: str, source_lang: str | None = None) -> dict:
    """Translate arbitrary free text. Real (Google Cloud Translation) when a
    key is configured; with no key, the text is returned unmodified and
    clearly marked `demo: True` -- fabricating a translation would be worse
    than admitting the capability isn't available."""
    if settings.GOOGLE_TRANSLATE_API_KEY:
        try:
            resp = httpx.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": settings.GOOGLE_TRANSLATE_API_KEY},
                json={
                    "q": text, "target": target_lang,
                    **({"source": source_lang} if source_lang else {}),
                },
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
            translation = data["data"]["translations"][0]
            return {
                "text": translation["translatedText"], "demo": False,
                "detected_source_lang": translation.get("detectedSourceLanguage"),
            }
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            logger.warning("Translation API request failed, falling back: %s", e)

    return {
        "text": text, "demo": True,
        "note": "Live translation is unavailable in demo mode; showing the original text.",
    }
