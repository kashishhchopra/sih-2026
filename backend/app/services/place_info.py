"""Location-aware content for the Multilingual Guide's Directions/Food/
Shopping categories (see services/translation.py for the plain-phrase
Greetings category, which needs none of this): real data about the
tourist's current surroundings -- their zone/safety status, nearest
emergency services, and live nearby food/shops -- substituted into a
curated, pre-translated sentence template.

Never a live-translated (i.e. possibly wrong) sentence, and never a
fabricated fact about a place: only real rows from the database or a live
OpenStreetMap lookup go into the template, same rule as
services/discovery.py and services/copilot.py. `demo: True` marks a
response using an English-fallback template because `target_lang` isn't
one of the languages this module has real, reviewed template text for --
same honesty rule as services/translation.py.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.police import PoliceUnit
from app.models.tourist import Tourist
from app.models.zone import Zone
from app.services import discovery
from app.services.geo import haversine_m, zones_containing_point
from app.services.safety import band_for

logger = logging.getLogger(__name__)

_RISK_LEVELS = ("low", "medium", "high", "restricted")
_BAND_LEVELS = ("safe", "moderate", "risky", "danger")

_RISK_WORDS: dict[str, dict[str, str]] = {
    "en": dict(zip(_RISK_LEVELS, ["low", "medium", "high", "restricted"])),
    "hi": dict(zip(_RISK_LEVELS, ["कम", "मध्यम", "उच्च", "प्रतिबंधित"])),
    "fr": dict(zip(_RISK_LEVELS, ["faible", "moyen", "élevé", "restreint"])),
    "de": dict(zip(_RISK_LEVELS, ["niedrig", "mittel", "hoch", "gesperrt"])),
    "es": dict(zip(_RISK_LEVELS, ["bajo", "medio", "alto", "restringido"])),
    "ja": dict(zip(_RISK_LEVELS, ["低", "中", "高", "制限"])),
    "zh": dict(zip(_RISK_LEVELS, ["低", "中", "高", "受限"])),
    "ko": dict(zip(_RISK_LEVELS, ["낮음", "보통", "높음", "제한구역"])),
    "ar": dict(zip(_RISK_LEVELS, ["منخفض", "متوسط", "مرتفع", "مقيد"])),
    "as": dict(zip(_RISK_LEVELS, ["কম", "মধ্যম", "উচ্চ", "নিষিদ্ধ"])),
    "bn": dict(zip(_RISK_LEVELS, ["কম", "মাঝারি", "উচ্চ", "নিষিদ্ধ"])),
    "gu": dict(zip(_RISK_LEVELS, ["ઓછું", "મધ્યમ", "ઊંચું", "પ્રતિબંધિત"])),
    "it": dict(zip(_RISK_LEVELS, ["basso", "medio", "alto", "limitato"])),
    "kn": dict(zip(_RISK_LEVELS, ["ಕಡಿಮೆ", "ಮಧ್ಯಮ", "ಹೆಚ್ಚು", "ನಿರ್ಬಂಧಿತ"])),
    "ml": dict(zip(_RISK_LEVELS, ["കുറവ്", "ഇടത്തരം", "ഉയർന്നത്", "നിയന്ത്രിതം"])),
    "mr": dict(zip(_RISK_LEVELS, ["कमी", "मध्यम", "जास्त", "प्रतिबंधित"])),
    "pa": dict(zip(_RISK_LEVELS, ["ਘੱਟ", "ਦਰਮਿਆਨਾ", "ਵੱਧ", "ਪਾਬੰਦੀਸ਼ੁਦਾ"])),
    "pt": dict(zip(_RISK_LEVELS, ["baixo", "médio", "alto", "restrito"])),
    "ru": dict(zip(_RISK_LEVELS, ["низкий", "средний", "высокий", "ограниченный"])),
    "ta": dict(zip(_RISK_LEVELS, ["குறைவு", "நடுத்தரம்", "அதிகம்", "தடைசெய்யப்பட்டது"])),
    "te": dict(zip(_RISK_LEVELS, ["తక్కువ", "మధ్యస్థం", "ఎక్కువ", "నిషేధిత"])),
}

_BAND_WORDS: dict[str, dict[str, str]] = {
    "en": dict(zip(_BAND_LEVELS, ["safe", "moderate", "risky", "danger"])),
    "hi": dict(zip(_BAND_LEVELS, ["सुरक्षित", "मध्यम", "जोखिमपूर्ण", "खतरनाक"])),
    "fr": dict(zip(_BAND_LEVELS, ["sûr", "modéré", "risqué", "dangereux"])),
    "de": dict(zip(_BAND_LEVELS, ["sicher", "mäßig", "riskant", "gefährlich"])),
    "es": dict(zip(_BAND_LEVELS, ["seguro", "moderado", "arriesgado", "peligroso"])),
    "ja": dict(zip(_BAND_LEVELS, ["安全", "中程度", "危険性あり", "危険"])),
    "zh": dict(zip(_BAND_LEVELS, ["安全", "中等", "有风险", "危险"])),
    "ko": dict(zip(_BAND_LEVELS, ["안전", "보통", "위험 가능성", "위험"])),
    "ar": dict(zip(_BAND_LEVELS, ["آمن", "متوسط", "محفوف بالمخاطر", "خطير"])),
    "as": dict(zip(_BAND_LEVELS, ["সুৰক্ষিত", "মধ্যম", "বিপদজনক", "সংকটপূৰ্ণ"])),
    "bn": dict(zip(_BAND_LEVELS, ["নিরাপদ", "মাঝারি", "ঝুঁকিপূর্ণ", "বিপজ্জনক"])),
    "gu": dict(zip(_BAND_LEVELS, ["સુરક્ષિત", "મધ્યમ", "જોખમી", "ખતરનાક"])),
    "it": dict(zip(_BAND_LEVELS, ["sicuro", "moderato", "rischioso", "pericoloso"])),
    "kn": dict(zip(_BAND_LEVELS, ["ಸುರಕ್ಷಿತ", "ಮಧ್ಯಮ", "ಅಪಾಯಕಾರಿ", "ಅಪಾಯ"])),
    "ml": dict(zip(_BAND_LEVELS, ["സുരക്ഷിതം", "ഇടത്തരം", "അപകടസാധ്യതയുള്ളത്", "അപകടകരം"])),
    "mr": dict(zip(_BAND_LEVELS, ["सुरक्षित", "मध्यम", "धोकादायक", "अतिधोकादायक"])),
    "pa": dict(zip(_BAND_LEVELS, ["ਸੁਰੱਖਿਅਤ", "ਦਰਮਿਆਨਾ", "ਜੋਖਮ ਭਰਿਆ", "ਖਤਰਨਾਕ"])),
    "pt": dict(zip(_BAND_LEVELS, ["seguro", "moderado", "arriscado", "perigoso"])),
    "ru": dict(zip(_BAND_LEVELS, ["безопасно", "умеренно", "рискованно", "опасно"])),
    "ta": dict(zip(_BAND_LEVELS, ["பாதுகாப்பானது", "நடுத்தரம்", "ஆபத்தானது", "மிக ஆபத்தானது"])),
    "te": dict(zip(_BAND_LEVELS, ["సురక్షితం", "మధ్యస్థం", "ప్రమాదకరం", "అత్యంత ప్రమాదకరం"])),
}

# Curated sentence templates, one real reviewed version per language --
# never a live-translated string. {placeholders} are substituted after
# picking the template, so proper nouns (zone/place names) and numbers are
# never themselves translated (same as leaving "Golden Gate Bridge"
# untranslated on a real map).
_TEMPLATES: dict[str, dict[str, str]] = {
    "zone_in": {
        "en": "You're in \"{zone}\" ({risk} risk). Your current safety status: {band}.",
        "hi": "आप \"{zone}\" में हैं ({risk} जोखिम)। आपकी वर्तमान सुरक्षा स्थिति: {band}।",
        "fr": "Vous êtes dans « {zone} » (risque {risk}). Votre statut de sécurité actuel : {band}.",
        "de": "Sie befinden sich in „{zone}\" (Risiko: {risk}). Ihr aktueller Sicherheitsstatus: {band}.",
        "es": "Estás en \"{zone}\" (riesgo {risk}). Tu estado de seguridad actual: {band}.",
        "ja": "現在「{zone}」内にいます（リスク：{risk}）。現在の安全状態：{band}。",
        "zh": "您目前在\"{zone}\"内（风险等级：{risk}）。当前安全状态：{band}。",
        "ko": "현재 \"{zone}\"에 있습니다 (위험도: {risk}). 현재 안전 상태: {band}.",
        "ar": "أنت في \"{zone}\" (خطورة {risk}). حالتك الأمنية الحالية: {band}.",
        "as": "আপুনি \"{zone}\"ৰ ভিতৰত আছে ({risk} বিপদ)। আপোনাৰ বৰ্তমান সুৰক্ষা অৱস্থা: {band}।",
        "bn": "আপনি \"{zone}\"-এ আছেন ({risk} ঝুঁকি)। আপনার বর্তমান নিরাপত্তা অবস্থা: {band}।",
        "gu": "તમે \"{zone}\"માં છો ({risk} જોખમ). તમારી વર્તમાન સુરક્ષા સ્થિતિ: {band}.",
        "it": "Sei in \"{zone}\" (rischio {risk}). Il tuo stato di sicurezza attuale: {band}.",
        "kn": "ನೀವು \"{zone}\" ನಲ್ಲಿ ಇದ್ದೀರಿ ({risk} ಅಪಾಯ). ನಿಮ್ಮ ಪ್ರಸ್ತುತ ಸುರಕ್ಷತಾ ಸ್ಥಿತಿ: {band}.",
        "ml": "നിങ്ങൾ \"{zone}\" ൽ ആണ് ({risk} അപകടസാധ്യത). നിങ്ങളുടെ നിലവിലെ സുരക്ഷാ നില: {band}.",
        "mr": "तुम्ही \"{zone}\" मध्ये आहात ({risk} धोका). तुमची सध्याची सुरक्षा स्थिती: {band}.",
        "pa": "ਤੁਸੀਂ \"{zone}\" ਵਿੱਚ ਹੋ ({risk} ਜੋਖਮ)। ਤੁਹਾਡੀ ਮੌਜੂਦਾ ਸੁਰੱਖਿਆ ਸਥਿਤੀ: {band}।",
        "pt": "Você está em \"{zone}\" (risco {risk}). Seu status de segurança atual: {band}.",
        "ru": "Вы находитесь в «{zone}» (уровень риска: {risk}). Ваш текущий статус безопасности: {band}.",
        "ta": "நீங்கள் \"{zone}\" இல் இருக்கிறீர்கள் ({risk} ஆபத்து). உங்கள் தற்போதைய பாதுகாப்பு நிலை: {band}.",
        "te": "మీరు \"{zone}\" లో ఉన్నారు ({risk} ప్రమాదం). మీ ప్రస్తుత భద్రతా స్థితి: {band}.",
    },
    "zone_open": {
        "en": "You're in an open area with no marked risk zone. Your current safety status: {band}.",
        "hi": "आप एक खुले क्षेत्र में हैं जहाँ कोई निर्धारित जोखिम क्षेत्र नहीं है। आपकी वर्तमान सुरक्षा स्थिति: {band}।",
        "fr": "Vous êtes dans une zone ouverte sans zone à risque définie. Votre statut de sécurité actuel : {band}.",
        "de": "Sie befinden sich in einem offenen Gebiet ohne ausgewiesene Risikozone. Ihr aktueller Sicherheitsstatus: {band}.",
        "es": "Estás en una zona abierta sin zona de riesgo definida. Tu estado de seguridad actual: {band}.",
        "ja": "現在、指定された危険区域のない開けた場所にいます。現在の安全状態：{band}。",
        "zh": "您目前处于没有标明风险区域的开放地带。当前安全状态：{band}。",
        "ko": "지정된 위험 구역이 없는 개방된 지역에 있습니다. 현재 안전 상태: {band}.",
        "ar": "أنت في منطقة مفتوحة بدون منطقة خطر محددة. حالتك الأمنية الحالية: {band}.",
        "as": "আপুনি এক মুকলি অঞ্চলত আছে য'ত কোনো নিৰ্ধাৰিত বিপদজনক এলেকা নাই। আপোনাৰ বৰ্তমান সুৰক্ষা অৱস্থা: {band}।",
        "bn": "আপনি একটি খোলা এলাকায় আছেন যেখানে কোনো নির্দিষ্ট ঝুঁকিপূর্ণ অঞ্চল নেই। আপনার বর্তমান নিরাপত্তা অবস্থা: {band}।",
        "gu": "તમે એક ખુલ્લા વિસ્તારમાં છો જ્યાં કોઈ નિર્ધારિત જોખમી ઝોન નથી. તમારી વર્તમાન સુરક્ષા સ્થિતિ: {band}.",
        "it": "Sei in una zona aperta senza un'area a rischio definita. Il tuo stato di sicurezza attuale: {band}.",
        "kn": "ನೀವು ಯಾವುದೇ ಗುರುತಿಸಲಾದ ಅಪಾಯದ ವಲಯವಿಲ್ಲದ ತೆರೆದ ಪ್ರದೇಶದಲ್ಲಿ ಇದ್ದೀರಿ. ನಿಮ್ಮ ಪ್ರಸ್ತುತ ಸುರಕ್ಷತಾ ಸ್ಥಿತಿ: {band}.",
        "ml": "നിർണ്ണയിക്കപ്പെട്ട അപകട മേഖലയില്ലാത്ത തുറന്ന സ്ഥലത്താണ് നിങ്ങൾ. നിങ്ങളുടെ നിലവിലെ സുരക്ഷാ നില: {band}.",
        "mr": "तुम्ही एका मोकळ्या भागात आहात जिथे कोणताही निश्चित धोकादायक क्षेत्र नाही. तुमची सध्याची सुरक्षा स्थिती: {band}.",
        "pa": "ਤੁਸੀਂ ਇੱਕ ਖੁੱਲੇ ਖੇਤਰ ਵਿੱਚ ਹੋ ਜਿੱਥੇ ਕੋਈ ਨਿਰਧਾਰਿਤ ਜੋਖਮ ਖੇਤਰ ਨਹੀਂ ਹੈ। ਤੁਹਾਡੀ ਮੌਜੂਦਾ ਸੁਰੱਖਿਆ ਸਥਿਤੀ: {band}।",
        "pt": "Você está em uma área aberta sem zona de risco definida. Seu status de segurança atual: {band}.",
        "ru": "Вы находитесь на открытой территории без обозначенной зоны риска. Ваш текущий статус безопасности: {band}.",
        "ta": "குறிப்பிட்ட ஆபத்து மண்டலம் இல்லாத திறந்த பகுதியில் நீங்கள் இருக்கிறீர்கள். உங்கள் தற்போதைய பாதுகாப்பு நிலை: {band}.",
        "te": "నిర్దిష్ట ప్రమాద మండలం లేని బహిరంగ ప్రదేశంలో మీరు ఉన్నారు. మీ ప్రస్తుత భద్రతా స్థితి: {band}.",
    },
    "no_location": {
        "en": "Turn on location tracking so I can tell you about this place.",
        "hi": "कृपया लोकेशन ट्रैकिंग चालू करें ताकि मैं आपको इस स्थान के बारे में बता सकूँ।",
        "fr": "Activez le suivi de localisation pour que je puisse vous renseigner sur cet endroit.",
        "de": "Aktivieren Sie die Standortverfolgung, damit ich Ihnen etwas über diesen Ort erzählen kann.",
        "es": "Activa el seguimiento de ubicación para que pueda contarte sobre este lugar.",
        "ja": "この場所について案内できるよう、位置情報の追跡をオンにしてください。",
        "zh": "请开启位置追踪，这样我才能告诉您这个地方的信息。",
        "ko": "이 장소에 대해 알려드릴 수 있도록 위치 추적을 켜주세요.",
        "ar": "يرجى تفعيل تتبع الموقع حتى أتمكن من إخبارك عن هذا المكان.",
        "as": "এই ঠাইখনৰ বিষয়ে জনাবলৈ অনুগ্ৰহ কৰি লোকেচন ট্ৰেকিং অন কৰক।",
        "bn": "এই জায়গা সম্পর্কে জানাতে অনুগ্রহ করে লোকেশন ট্র্যাকিং চালু করুন।",
        "gu": "આ સ્થળ વિશે જણાવવા માટે કૃપા કરી લોકેશન ટ્રેકિંગ ચાલુ કરો.",
        "it": "Attiva il tracciamento della posizione così posso dirti qualcosa su questo posto.",
        "kn": "ಈ ಸ್ಥಳದ ಬಗ್ಗೆ ಹೇಳಲು ದಯವಿಟ್ಟು ಲೊಕೇಶನ್ ಟ್ರ್ಯಾಕಿಂಗ್ ಆನ್ ಮಾಡಿ.",
        "ml": "ഈ സ്ഥലത്തെക്കുറിച്ച് പറയാൻ ദയവായി ലൊക്കേഷൻ ട്രാക്കിംഗ് ഓണാക്കുക.",
        "mr": "या ठिकाणाबद्दल सांगण्यासाठी कृपया लोकेशन ट्रॅकिंग सुरू करा.",
        "pa": "ਇਸ ਜਗ੍ਹਾ ਬਾਰੇ ਦੱਸਣ ਲਈ ਕਿਰਪਾ ਕਰਕੇ ਲੋਕੇਸ਼ਨ ਟਰੈਕਿੰਗ ਚਾਲੂ ਕਰੋ।",
        "pt": "Ative o rastreamento de localização para que eu possa te contar sobre este lugar.",
        "ru": "Включите отслеживание местоположения, чтобы я мог рассказать вам об этом месте.",
        "ta": "இந்த இடத்தைப் பற்றி சொல்ல, தயவுசெய்து லொகேஷன் டிராக்கிங்கை இயக்கவும்.",
        "te": "ఈ ప్రదేశం గురించి చెప్పడానికి దయచేసి లొకేషన్ ట్రాకింగ్‌ను ఆన్ చేయండి.",
    },
    "how_far": {
        "en": "Nearest hospital: {hospital} ({hkm} km away). Nearest police: {police} ({pkm} km away).",
        "hi": "निकटतम अस्पताल: {hospital} ({hkm} किमी दूर)। निकटतम पुलिस: {police} ({pkm} किमी दूर)।",
        "fr": "Hôpital le plus proche : {hospital} ({hkm} km). Police la plus proche : {police} ({pkm} km).",
        "de": "Nächstes Krankenhaus: {hospital} ({hkm} km entfernt). Nächste Polizei: {police} ({pkm} km entfernt).",
        "es": "Hospital más cercano: {hospital} ({hkm} km). Policía más cercana: {police} ({pkm} km).",
        "ja": "最寄りの病院：{hospital}（{hkm} km）。最寄りの警察：{police}（{pkm} km）。",
        "zh": "最近的医院：{hospital}（{hkm} 公里）。最近的警察局：{police}（{pkm} 公里）。",
        "ko": "가장 가까운 병원: {hospital} ({hkm} km). 가장 가까운 경찰서: {police} ({pkm} km).",
        "ar": "أقرب مستشفى: {hospital} (على بعد {hkm} كم). أقرب مركز شرطة: {police} (على بعد {pkm} كم).",
        "as": "ওচৰৰ চিকিৎসালয়: {hospital} ({hkm} কিমি দূৰত্ব)। ওচৰৰ আৰক্ষী: {police} ({pkm} কিমি দূৰত্ব)।",
        "bn": "নিকটতম হাসপাতাল: {hospital} ({hkm} কিমি দূরে)। নিকটতম পুলিশ: {police} ({pkm} কিমি দূরে)।",
        "gu": "નજીકની હોસ્પિટલ: {hospital} ({hkm} કિમી દૂર). નજીકનું પોલીસ સ્ટેશન: {police} ({pkm} કિમી દૂર).",
        "it": "Ospedale più vicino: {hospital} ({hkm} km). Polizia più vicina: {police} ({pkm} km).",
        "kn": "ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆ: {hospital} ({hkm} ಕಿ.ಮೀ ದೂರ). ಹತ್ತಿರದ ಪೊಲೀಸ್: {police} ({pkm} ಕಿ.ಮೀ ದೂರ).",
        "ml": "അടുത്തുള്ള ആശുപത്രി: {hospital} ({hkm} കി.മീ അകലെ). അടുത്തുള്ള പോലീസ്: {police} ({pkm} കി.മീ അകലെ).",
        "mr": "जवळचे रुग्णालय: {hospital} ({hkm} किमी दूर). जवळचे पोलीस: {police} ({pkm} किमी दूर).",
        "pa": "ਨਜ਼ਦੀਕੀ ਹਸਪਤਾਲ: {hospital} ({hkm} ਕਿਲੋਮੀਟਰ ਦੂਰ)। ਨਜ਼ਦੀਕੀ ਪੁਲਿਸ: {police} ({pkm} ਕਿਲੋਮੀਟਰ ਦੂਰ)।",
        "pt": "Hospital mais próximo: {hospital} ({hkm} km). Polícia mais próxima: {police} ({pkm} km).",
        "ru": "Ближайшая больница: {hospital} ({hkm} км). Ближайшая полиция: {police} ({pkm} км).",
        "ta": "அருகிலுள்ள மருத்துவமனை: {hospital} ({hkm} கிமீ தொலைவில்). அருகிலுள்ள காவல் நிலையம்: {police} ({pkm} கிமீ தொலைவில்).",
        "te": "సమీప ఆసుపత్రి: {hospital} ({hkm} కి.మీ దూరం). సమీప పోలీస్: {police} ({pkm} కి.మీ దూరం).",
    },
    "food_found": {
        "en": "Nearby food to try: {list} (within {radius} km).",
        "hi": "आस-पास खाने के लिए: {list} ({radius} किमी के भीतर)।",
        "fr": "À proximité à essayer : {list} (dans un rayon de {radius} km).",
        "de": "Essen in der Nähe: {list} (im Umkreis von {radius} km).",
        "es": "Comida cercana para probar: {list} (a menos de {radius} km).",
        "ja": "近くのおすすめの食事：{list}（半径{radius} km以内）。",
        "zh": "附近可以尝试的美食：{list}（{radius} 公里范围内）。",
        "ko": "근처에서 먹어볼 만한 곳: {list} (반경 {radius} km 이내).",
        "ar": "أماكن طعام قريبة لتجربتها: {list} (ضمن {radius} كم).",
        "as": "ওচৰৰ খাদ্যৰ ঠাই: {list} ({radius} কিমিৰ ভিতৰত)।",
        "bn": "কাছাকাছি খাবারের জায়গা: {list} ({radius} কিমির মধ্যে)।",
        "gu": "નજીકમાં ખાવા માટે: {list} ({radius} કિમીની અંદર).",
        "it": "Cibo nelle vicinanze da provare: {list} (entro {radius} km).",
        "kn": "ಹತ್ತಿರದಲ್ಲಿ ಪ್ರಯತ್ನಿಸಲು ಆಹಾರ: {list} ({radius} ಕಿ.ಮೀ ಒಳಗೆ).",
        "ml": "അടുത്തുള്ള പരീക്ഷിക്കാവുന്ന ഭക്ഷണം: {list} ({radius} കി.മീ പരിധിയിൽ).",
        "mr": "जवळपास चाखण्यासारखे खाद्यपदार्थ: {list} ({radius} किमीच्या आत).",
        "pa": "ਨੇੜੇ ਖਾਣ ਲਈ: {list} ({radius} ਕਿਲੋਮੀਟਰ ਦੇ ਅੰਦਰ)।",
        "pt": "Comida por perto para experimentar: {list} (dentro de {radius} km).",
        "ru": "Рядом стоит попробовать: {list} (в радиусе {radius} км).",
        "ta": "அருகில் முயற்சிக்க வேண்டிய உணவகங்கள்: {list} ({radius} கிமீக்குள்).",
        "te": "సమీపంలో ప్రయత్నించదగిన ఆహారం: {list} ({radius} కి.మీ లోపల).",
    },
    "food_empty": {
        "en": "No nearby food spots found right now — try the Discovery tab, or move a little and check again.",
        "hi": "अभी आस-पास कोई खाने की जगह नहीं मिली — डिस्कवरी टैब देखें या थोड़ा आगे बढ़कर फिर से जाँचें।",
        "fr": "Aucun endroit pour manger trouvé à proximité pour l'instant — consultez l'onglet Découverte ou réessayez après vous être déplacé.",
        "de": "Derzeit keine Essensmöglichkeiten in der Nähe gefunden — schauen Sie im Entdecken-Tab nach oder versuchen Sie es später erneut.",
        "es": "No se encontraron lugares para comer cerca por ahora — revisa la pestaña Discovery o vuelve a intentarlo tras moverte un poco.",
        "ja": "近くに食事スポットが見つかりませんでした。ディスカバリー タブを確認するか、少し移動してから再度確認してください。",
        "zh": "目前附近没有找到用餐地点——请查看\"探索\"标签，或稍后移动位置再试。",
        "ko": "지금은 근처에서 음식점을 찾지 못했습니다 — 탐색 탭을 확인하거나 조금 이동한 후 다시 확인해 주세요.",
        "ar": "لم يتم العثور على أماكن طعام قريبة الآن — تحقق من علامة تبويب الاستكشاف أو حاول مرة أخرى بعد التحرك قليلاً.",
        "as": "এতিয়া ওচৰত কোনো খাদ্যৰ ঠাই পোৱা নগ'ল — ডিস্কভাৰী টেব চাওক অথবা অলপ আগবাঢ়ি আকৌ চেষ্টা কৰক।",
        "bn": "এখন কাছাকাছি কোনো খাবারের জায়গা পাওয়া যায়নি — ডিসকভারি ট্যাব দেখুন অথবা একটু এগিয়ে আবার চেষ্টা করুন।",
        "gu": "અત્યારે નજીકમાં કોઈ ખાવાની જગ્યા મળી નથી — ડિસ્કવરી ટેબ તપાસો અથવા થોડું આગળ વધીને ફરી પ્રયાસ કરો.",
        "it": "Nessun posto per mangiare trovato nelle vicinanze al momento — controlla la scheda Discovery o riprova dopo esserti spostato.",
        "kn": "ಈಗ ಹತ್ತಿರದಲ್ಲಿ ಯಾವುದೇ ಆಹಾರ ಸ್ಥಳಗಳು ಕಂಡುಬಂದಿಲ್ಲ — ಡಿಸ್ಕವರಿ ಟ್ಯಾಬ್ ಪರಿಶೀಲಿಸಿ ಅಥವಾ ಸ್ವಲ್ಪ ಚಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "ml": "ഇപ്പോൾ അടുത്ത് ഭക്ഷണ സ്ഥലങ്ങളൊന്നും കണ്ടെത്തിയില്ല — ഡിസ്‌കവറി ടാബ് നോക്കുക അല്ലെങ്കിൽ അല്പം നീങ്ങിയ ശേഷം വീണ്ടും ശ്രമിക്കുക.",
        "mr": "सध्या जवळपास कोणतीही खाद्य ठिकाणे सापडली नाहीत — डिस्कव्हरी टॅब पहा किंवा थोडे पुढे जाऊन पुन्हा प्रयत्न करा.",
        "pa": "ਹੁਣ ਨੇੜੇ ਕੋਈ ਖਾਣ ਦੀ ਜਗ੍ਹਾ ਨਹੀਂ ਮਿਲੀ — ਡਿਸਕਵਰੀ ਟੈਬ ਵੇਖੋ ਜਾਂ ਥੋੜ੍ਹਾ ਅੱਗੇ ਵਧ ਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "pt": "Nenhum lugar para comer encontrado por perto agora — confira a aba Discovery ou tente novamente depois de se mover um pouco.",
        "ru": "Поблизости пока не найдено мест, где поесть — проверьте вкладку «Открытия» или попробуйте снова, немного переместившись.",
        "ta": "இப்போது அருகில் உணவகங்கள் எதுவும் கிடைக்கவில்லை — டிஸ்கவரி தாவலைப் பார்க்கவும் அல்லது சிறிது நகர்ந்து மீண்டும் முயற்சிக்கவும்.",
        "te": "ప్రస్తుతం సమీపంలో ఆహార స్థలాలు కనుగొనబడలేదు — డిస్కవరీ ట్యాబ్‌ను చూడండి లేదా కొంచెం ముందుకు వెళ్లి మళ్లీ ప్రయత్నించండి.",
    },
    "shopping_found": {
        "en": "Nearby shops to check out: {list} (within {radius} km).",
        "hi": "आस-पास की दुकानें: {list} ({radius} किमी के भीतर)।",
        "fr": "Boutiques à proximité : {list} (dans un rayon de {radius} km).",
        "de": "Geschäfte in der Nähe: {list} (im Umkreis von {radius} km).",
        "es": "Tiendas cercanas: {list} (a menos de {radius} km).",
        "ja": "近くのお店：{list}（半径{radius} km以内）。",
        "zh": "附近的商店：{list}（{radius} 公里范围内）。",
        "ko": "근처 상점: {list} (반경 {radius} km 이내).",
        "ar": "متاجر قريبة: {list} (ضمن {radius} كم).",
        "as": "ওচৰৰ দোকান: {list} ({radius} কিমিৰ ভিতৰত)।",
        "bn": "কাছাকাছি দোকান: {list} ({radius} কিমির মধ্যে)।",
        "gu": "નજીકની દુકાનો: {list} ({radius} કિમીની અંદર).",
        "it": "Negozi nelle vicinanze: {list} (entro {radius} km).",
        "kn": "ಹತ್ತಿರದ ಅಂಗಡಿಗಳು: {list} ({radius} ಕಿ.ಮೀ ಒಳಗೆ).",
        "ml": "അടുത്തുള്ള കടകൾ: {list} ({radius} കി.മീ പരിധിയിൽ).",
        "mr": "जवळपासची दुकाने: {list} ({radius} किमीच्या आत).",
        "pa": "ਨੇੜਲੀਆਂ ਦੁਕਾਨਾਂ: {list} ({radius} ਕਿਲੋਮੀਟਰ ਦੇ ਅੰਦਰ)।",
        "pt": "Lojas por perto: {list} (dentro de {radius} km).",
        "ru": "Магазины поблизости: {list} (в радиусе {radius} км).",
        "ta": "அருகிலுள்ள கடைகள்: {list} ({radius} கிமீக்குள்).",
        "te": "సమీపంలోని దుకాణాలు: {list} ({radius} కి.మీ లోపల).",
    },
    "shopping_empty": {
        "en": "No nearby shops found right now — try again once you've moved a bit.",
        "hi": "अभी आस-पास कोई दुकान नहीं मिली — थोड़ा आगे बढ़कर फिर से जाँचें।",
        "fr": "Aucune boutique trouvée à proximité pour l'instant — réessayez après vous être déplacé.",
        "de": "Derzeit keine Geschäfte in der Nähe gefunden — versuchen Sie es später erneut.",
        "es": "No se encontraron tiendas cercanas por ahora — vuelve a intentarlo tras moverte un poco.",
        "ja": "近くにお店が見つかりませんでした。少し移動してから再度確認してください。",
        "zh": "目前附近没有找到商店——请稍后移动位置再试。",
        "ko": "지금은 근처에서 상점을 찾지 못했습니다 — 조금 이동한 후 다시 확인해 주세요.",
        "ar": "لم يتم العثور على متاجر قريبة الآن — حاول مرة أخرى بعد التحرك قليلاً.",
        "as": "এতিয়া ওচৰত কোনো দোকান পোৱা নগ'ল — অলপ আগবাঢ়ি আকৌ চেষ্টা কৰক।",
        "bn": "এখন কাছাকাছি কোনো দোকান পাওয়া যায়নি — একটু এগিয়ে আবার চেষ্টা করুন।",
        "gu": "અત્યારે નજીકમાં કોઈ દુકાન મળી નથી — થોડું આગળ વધીને ફરી પ્રયાસ કરો.",
        "it": "Nessun negozio trovato nelle vicinanze al momento — riprova dopo esserti spostato.",
        "kn": "ಈಗ ಹತ್ತಿರದಲ್ಲಿ ಯಾವುದೇ ಅಂಗಡಿಗಳು ಕಂಡುಬಂದಿಲ್ಲ — ಸ್ವಲ್ಪ ಚಲಿಸಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
        "ml": "ഇപ്പോൾ അടുത്ത് കടകളൊന്നും കണ്ടെത്തിയില്ല — അല്പം നീങ്ങിയ ശേഷം വീണ്ടും ശ്രമിക്കുക.",
        "mr": "सध्या जवळपास कोणतीही दुकाने सापडली नाहीत — थोडे पुढे जाऊन पुन्हा प्रयत्न करा.",
        "pa": "ਹੁਣ ਨੇੜੇ ਕੋਈ ਦੁਕਾਨ ਨਹੀਂ ਮਿਲੀ — ਥੋੜ੍ਹਾ ਅੱਗੇ ਵਧ ਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "pt": "Nenhuma loja encontrada por perto agora — tente novamente depois de se mover um pouco.",
        "ru": "Поблизости пока не найдено магазинов — попробуйте снова, немного переместившись.",
        "ta": "இப்போது அருகில் கடைகள் எதுவும் கிடைக்கவில்லை — சிறிது நகர்ந்து மீண்டும் முயற்சிக்கவும்.",
        "te": "ప్రస్తుతం సమీపంలో దుకాణాలు కనుగొనబడలేదు — కొంచెం ముందుకు వెళ్లి మళ్లీ ప్రయత్నించండి.",
    },
}


def _template(key: str, lang: str) -> tuple[str, bool]:
    variants = _TEMPLATES[key]
    if lang in variants:
        return variants[lang], False
    return variants["en"], True


def _risk_word(level: str, lang: str) -> str:
    return _RISK_WORDS.get(lang, _RISK_WORDS["en"]).get(level, level)


def _band_word(band: str, lang: str) -> str:
    return _BAND_WORDS.get(lang, _BAND_WORDS["en"]).get(band, band)


def no_location_message(lang: str) -> dict:
    text, demo = _template("no_location", lang)
    return {"text": text, "demo": demo}


def describe_current_zone(db: Session, tourist: Tourist, lang: str) -> dict:
    """Directions > "Where is this place?": the tourist's real current zone
    (name + risk level) and overall safety status, or an honest prompt to
    enable tracking if there's no live location yet."""
    if tourist.last_lat is None or tourist.last_lng is None:
        text, demo = _template("no_location", lang)
        return {"text": text, "demo": demo}

    zones = db.query(Zone).all()
    inside = zones_containing_point(tourist.last_lat, tourist.last_lng, zones)
    band = band_for(tourist.safety_score)
    band_word = _band_word(band, lang)

    if not inside:
        text, demo = _template("zone_open", lang)
        return {"text": text.format(band=band_word), "demo": demo}

    worst = max(inside, key=lambda z: {"low": 0, "medium": 1, "high": 2, "restricted": 3}.get(z.risk_level, 1))
    text, demo = _template("zone_in", lang)
    return {"text": text.format(zone=worst.name, risk=_risk_word(worst.risk_level, lang), band=band_word), "demo": demo}


def describe_nearest_help(db: Session, tourist: Tourist, lang: str) -> dict:
    """Directions > "How far is it from here?": real distance to the
    nearest hospital and police unit from the tourist's current location."""
    if tourist.last_lat is None or tourist.last_lng is None:
        text, demo = _template("no_location", lang)
        return {"text": text, "demo": demo}

    units = db.query(PoliceUnit).filter(PoliceUnit.available.is_(True)).all()

    def nearest(unit_type: str) -> tuple[str, float] | tuple[None, None]:
        candidates = [u for u in units if u.unit_type == unit_type]
        if not candidates:
            return None, None
        u = min(candidates, key=lambda c: haversine_m(tourist.last_lat, tourist.last_lng, c.lat, c.lng))
        km = round(haversine_m(tourist.last_lat, tourist.last_lng, u.lat, u.lng) / 1000, 1)
        return u.name, km

    hospital_name, hospital_km = nearest("ambulance")
    police_name, police_km = nearest("police")
    text, demo = _template("how_far", lang)
    return {
        "text": text.format(
            hospital=hospital_name or "—", hkm=hospital_km if hospital_km is not None else "—",
            police=police_name or "—", pkm=police_km if police_km is not None else "—",
        ),
        "demo": demo,
    }


def describe_nearby_food(db: Session, lat: float, lng: float, lang: str, radius_km: float = 10.0) -> dict:
    """Food category: real nearby eateries (live OpenStreetMap, DB fallback
    -- see services/discovery.py) near the tourist's current location."""
    places = discovery.find_discovery(db, lat, lng, radius_km=radius_km, categories=["regional_food"])
    names = [p["name"] for p in places[:3]]
    if not names:
        text, demo = _template("food_empty", lang)
        return {"text": text, "demo": demo}
    text, demo = _template("food_found", lang)
    return {"text": text.format(list=", ".join(names), radius=radius_km), "demo": demo}


_SHOP_OVERPASS_QUERY = """
[out:json][timeout:{timeout}];
(
  node["shop"]["name"](around:{radius_m},{lat},{lng});
);
out center tags;
"""


def _fetch_nearby_shop_names(lat: float, lng: float, radius_km: float) -> list[str]:
    """Real named shops from live OpenStreetMap Overpass. Returns an empty
    list (never a guess) if the lookup is disabled, unreachable, or times
    out -- same fallback discipline as services/discovery.py."""
    if not settings.DISCOVERY_LIVE_ENABLED:
        return []
    query = _SHOP_OVERPASS_QUERY.format(
        timeout=int(settings.OVERPASS_TIMEOUT_SECONDS), radius_m=int(radius_km * 1000), lat=lat, lng=lng,
    )
    try:
        resp = httpx.post(
            settings.OVERPASS_API_URL, data={"data": query},
            headers={"User-Agent": "musafir-smart-tourist-safety/1.0 (shopping lookup)"},
            timeout=settings.OVERPASS_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Overpass shopping request failed: %s", e)
        return []

    names: list[str] = []
    for el in elements:
        name = el.get("tags", {}).get("name")
        if name and name not in names:
            names.append(name)
    return names


def describe_nearby_shopping(lat: float, lng: float, lang: str, radius_km: float = 10.0) -> dict:
    """Shopping category: real nearby named shops (live OpenStreetMap) near
    the tourist's current location."""
    names = _fetch_nearby_shop_names(lat, lng, radius_km)[:3]
    if not names:
        text, demo = _template("shopping_empty", lang)
        return {"text": text, "demo": demo}
    text, demo = _template("shopping_found", lang)
    return {"text": text.format(list=", ".join(names), radius=radius_km), "demo": demo}
