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
            "as": "নমস্কাৰ", "bn": "নমস্কার", "gu": "નમસ્તે", "it": "Ciao",
            "kn": "ನಮಸ್ಕಾರ", "ml": "നമസ്കാരം", "mr": "नमस्कार", "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ",
            "pt": "Olá", "ru": "Привет", "ta": "வணக்கம்", "te": "నమస్కారం",
        },
        "goodbye": {
            "en": "Goodbye", "hi": "अलविदा", "fr": "Au revoir", "de": "Auf Wiedersehen",
            "es": "Adiós", "ja": "さようなら", "zh": "再见", "ko": "안녕히 가세요", "ar": "وداعاً",
            "as": "বিদায়", "bn": "বিদায়", "gu": "આવજો", "it": "Arrivederci",
            "kn": "ವಿದಾಯ", "ml": "വിട", "mr": "निरोप", "pa": "ਅਲਵਿਦਾ",
            "pt": "Adeus", "ru": "До свидания", "ta": "போய் வருகிறேன்", "te": "వీడ్కోలు",
        },
        "please": {
            "en": "Please", "hi": "कृपया", "fr": "S'il vous plaît", "de": "Bitte",
            "es": "Por favor", "ja": "お願いします", "zh": "请", "ko": "부탁합니다", "ar": "من فضلك",
            "as": "অনুগ্ৰহ কৰি", "bn": "অনুগ্রহ করে", "gu": "કૃપા કરીને", "it": "Per favore",
            "kn": "ದಯವಿಟ್ಟು", "ml": "ദയവായി", "mr": "कृपया", "pa": "ਕਿਰਪਾ ਕਰਕੇ",
            "pt": "Por favor", "ru": "Пожалуйста", "ta": "தயவுசெய்து", "te": "దయచేసి",
        },
    },
    "directions": {
        "where_is_this": {
            "en": "Where is this place?", "hi": "यह जगह कहाँ है?", "fr": "Où est cet endroit ?",
            "de": "Wo ist dieser Ort?", "es": "¿Dónde está este lugar?", "ja": "この場所はどこですか。",
            "zh": "这个地方在哪里？", "ko": "이곳이 어디예요?", "ar": "أين هذا المكان؟",
            "as": "এই ঠাইখন ক'ত?", "bn": "এই জায়গাটা কোথায়?", "gu": "આ સ્થળ ક્યાં છે?",
            "it": "Dov'è questo posto?", "kn": "ಈ ಸ್ಥಳ ಎಲ್ಲಿದೆ?", "ml": "ഈ സ്ഥലം എവിടെയാണ്?",
            "mr": "हे ठिकाण कुठे आहे?", "pa": "ਇਹ ਜਗ੍ਹਾ ਕਿੱਥੇ ਹੈ?", "pt": "Onde fica este lugar?",
            "ru": "Где это место?", "ta": "இந்த இடம் எங்கே?", "te": "ఈ స్థలం ఎక్కడ ఉంది?",
        },
        "how_far": {
            "en": "How far is it from here?", "hi": "यहाँ से कितनी दूर है?",
            "fr": "C'est à quelle distance d'ici ?", "de": "Wie weit ist es von hier?",
            "es": "¿A qué distancia está de aquí?", "ja": "ここからどのくらい遠いですか。",
            "zh": "从这里有多远？", "ko": "여기서 얼마나 멀어요?", "ar": "كم تبعد من هنا؟",
            "as": "ইয়াৰ পৰা কিমান দূৰ?", "bn": "এখান থেকে কতদূর?", "gu": "અહીંથી કેટલું દૂર છે?",
            "it": "Quanto dista da qui?", "kn": "ಇಲ್ಲಿಂದ ಎಷ್ಟು ದೂರ?", "ml": "ഇവിടെ നിന്ന് എത്ര ദൂരമുണ്ട്?",
            "mr": "इथून किती लांब आहे?", "pa": "ਇੱਥੋਂ ਕਿੰਨੀ ਦੂਰ ਹੈ?", "pt": "A que distância fica daqui?",
            "ru": "Как далеко это отсюда?", "ta": "இங்கிருந்து எவ்வளவு தூரம்?", "te": "ఇక్కడి నుండి ఎంత దూరం?",
        },
    },
    "food": {
        "recommend_local_food": {
            "en": "Can you recommend a local dish?", "hi": "क्या आप कोई स्थानीय व्यंजन सुझा सकते हैं?",
            "fr": "Pouvez-vous recommander un plat local ?", "de": "Können Sie ein lokales Gericht empfehlen?",
            "es": "¿Puede recomendar un plato local?", "ja": "地元の料理を勧めてもらえますか。",
            "zh": "你能推荐一道当地菜吗？", "ko": "현지 음식을 추천해 주시겠어요?", "ar": "هل يمكنك أن توصي بطبق محلي؟",
            "as": "আপুনি এবিধ স্থানীয় খাদ্যৰ পৰামৰ্শ দিব পাৰিবনে?", "bn": "আপনি কি একটি স্থানীয় খাবারের পরামর্শ দিতে পারেন?",
            "gu": "શું તમે સ્થાનિક વાનગીની ભલામણ કરી શકો છો?", "it": "Puoi consigliarmi un piatto locale?",
            "kn": "ನೀವು ಸ್ಥಳೀಯ ಖಾದ್ಯವನ್ನು ಶಿಫಾರಸು ಮಾಡಬಹುದೇ?", "ml": "നിങ്ങൾക്ക് ഒരു പ്രാദേശിക വിഭവം ശുപാർശ ചെയ്യാമോ?",
            "mr": "तुम्ही एखादा स्थानिक पदार्थ सुचवू शकता का?", "pa": "ਕੀ ਤੁਸੀਂ ਕੋਈ ਸਥਾਨਕ ਪਕਵਾਨ ਸੁਝਾ ਸਕਦੇ ਹੋ?",
            "pt": "Você pode recomendar um prato local?", "ru": "Можете порекомендовать местное блюдо?",
            "ta": "நீங்கள் ஒரு உள்ளூர் உணவை பரிந்துரைக்க முடியுமா?", "te": "మీరు స్థానిక వంటకాన్ని సిఫారసు చేయగలరా?",
        },
        "vegetarian": {
            "en": "I am vegetarian.", "hi": "मैं शाकाहारी हूँ।", "fr": "Je suis végétarien(ne).",
            "de": "Ich bin Vegetarier(in).", "es": "Soy vegetariano/a.", "ja": "私はベジタリアンです。",
            "zh": "我吃素。", "ko": "저는 채식주의자예요.", "ar": "أنا نباتي.",
            "as": "মই নিৰামিষভোজী।", "bn": "আমি নিরামিষাশী।", "gu": "હું શાકાહારી છું.", "it": "Sono vegetariano/a.",
            "kn": "ನಾನು ಸಸ್ಯಾಹಾರಿ.", "ml": "ഞാൻ സസ്യാഹാരിയാണ്.", "mr": "मी शाकाहारी आहे.", "pa": "ਮੈਂ ਸ਼ਾਕਾਹਾਰੀ ਹਾਂ।",
            "pt": "Sou vegetariano/a.", "ru": "Я вегетарианец/вегетарианка.", "ta": "நான் சைவம்.", "te": "నేను శాకాహారిని.",
        },
    },
    "shopping": {
        "how_much": {
            "en": "How much does this cost?", "hi": "इसकी कीमत कितनी है?", "fr": "Combien ça coûte ?",
            "de": "Wie viel kostet das?", "es": "¿Cuánto cuesta esto?", "ja": "これはいくらですか。",
            "zh": "这个多少钱？", "ko": "이거 얼마예요?", "ar": "كم يكلف هذا؟",
            "as": "ইয়াৰ দাম কিমান?", "bn": "এটার দাম কত?", "gu": "આનો ભાવ કેટલો છે?", "it": "Quanto costa questo?",
            "kn": "ಇದರ ಬೆಲೆ ಎಷ್ಟು?", "ml": "ഇതിന്റെ വില എത്രയാണ്?", "mr": "याची किंमत किती आहे?",
            "pa": "ਇਸ ਦੀ ਕੀਮਤ ਕਿੰਨੀ ਹੈ?", "pt": "Quanto custa isto?", "ru": "Сколько это стоит?",
            "ta": "இதன் விலை என்ன?", "te": "దీని ధర ఎంత?",
        },
        "too_expensive": {
            "en": "That's too expensive.", "hi": "यह बहुत महँगा है।", "fr": "C'est trop cher.",
            "de": "Das ist zu teuer.", "es": "Eso es demasiado caro.", "ja": "それは高すぎます。",
            "zh": "太贵了。", "ko": "너무 비싸요.", "ar": "هذا غالٍ جداً.",
            "as": "এইটো বহুত দামী।", "bn": "এটা খুব দামি।", "gu": "આ ખૂબ મોંઘું છે.", "it": "È troppo caro.",
            "kn": "ಇದು ತುಂಬಾ ದುಬಾರಿಯಾಗಿದೆ.", "ml": "ഇത് വളരെ വിലയേറിയതാണ്.", "mr": "हे खूप महाग आहे.",
            "pa": "ਇਹ ਬਹੁਤ ਮਹਿੰਗਾ ਹੈ।", "pt": "Isso é muito caro.", "ru": "Это слишком дорого.",
            "ta": "இது மிகவும் விலை உயர்ந்தது.", "te": "ఇది చాలా ఖరీదైనది.",
        },
        "lower_price": {
            "en": "Can you lower the price a little?", "hi": "क्या आप कीमत थोड़ी कम कर सकते हैं?",
            "fr": "Pouvez-vous baisser un peu le prix ?", "de": "Können Sie den Preis etwas senken?",
            "es": "¿Puede bajar un poco el precio?", "ja": "少し値段を下げてもらえますか。",
            "zh": "可以便宜一点吗？", "ko": "가격을 조금 낮춰 주실 수 있나요?", "ar": "هل يمكنك خفض السعر قليلاً؟",
            "as": "আপুনি দামখিনি অলপ কমাব পাৰিবনে?", "bn": "আপনি কি দামটা একটু কমাতে পারবেন?",
            "gu": "શું તમે ભાવ થોડો ઓછો કરી શકો છો?", "it": "Può abbassare un po' il prezzo?",
            "kn": "ನೀವು ಬೆಲೆಯನ್ನು ಸ್ವಲ್ಪ ಕಡಿಮೆ ಮಾಡಬಹುದೇ?", "ml": "വില അല്പം കുറയ്ക്കാമോ?",
            "mr": "तुम्ही किंमत थोडी कमी करू शकता का?", "pa": "ਕੀ ਤੁਸੀਂ ਕੀਮਤ ਥੋੜ੍ਹੀ ਘਟਾ ਸਕਦੇ ਹੋ?",
            "pt": "Pode baixar um pouco o preço?", "ru": "Можете немного снизить цену?",
            "ta": "விலையை கொஞ்சம் குறைக்க முடியுமா?", "te": "ధరను కొంచెం తగ్గించగలరా?",
        },
        "final_price": {
            "en": "What is your final price?", "hi": "आपकी अंतिम कीमत क्या है?",
            "fr": "Quel est votre dernier prix ?", "de": "Was ist Ihr letzter Preis?",
            "es": "¿Cuál es su precio final?", "ja": "最終的な値段はいくらですか。",
            "zh": "你的最终价格是多少？", "ko": "최종 가격이 얼마예요?", "ar": "ما هو سعرك النهائي؟",
            "as": "আপোনাৰ অন্তিম দাম কিমান?", "bn": "আপনার শেষ দাম কত?", "gu": "તમારો છેલ્લો ભાવ શું છે?",
            "it": "Qual è il suo prezzo finale?", "kn": "ನಿಮ್ಮ ಅಂತಿಮ ಬೆಲೆ ಎಷ್ಟು?",
            "ml": "നിങ്ങളുടെ അവസാന വില എന്താണ്?", "mr": "तुमची अंतिम किंमत काय आहे?",
            "pa": "ਤੁਹਾਡੀ ਅੰਤਿਮ ਕੀਮਤ ਕੀ ਹੈ?", "pt": "Qual é o seu preço final?",
            "ru": "Какова ваша окончательная цена?", "ta": "உங்கள் இறுதி விலை என்ன?", "te": "మీ చివరి ధర ఎంత?",
        },
    },
    "medical": {
        "im_allergic": {
            "en": "I am allergic to nuts and peanuts.", "hi": "मुझे मेवों और मूंगफली से एलर्जी है।",
            "fr": "Je suis allergique aux noix et aux cacahuètes.", "de": "Ich bin allergisch gegen Nüsse und Erdnüsse.",
            "es": "Soy alérgico/a a los frutos secos y al maní.", "ja": "ナッツとピーナッツにアレルギーがあります。",
            "zh": "我对坚果和花生过敏。", "ko": "저는 견과류와 땅콩에 알레르기가 있어요.",
            "ar": "لدي حساسية من المكسرات والفول السوداني.",
        },
        "taking_medication": {
            "en": "I am taking medication. Please be careful.", "hi": "मैं दवा ले रहा/रही हूँ। कृपया सावधान रहें।",
            "fr": "Je prends des médicaments. Soyez prudent(e), s'il vous plaît.",
            "de": "Ich nehme Medikamente ein. Bitte seien Sie vorsichtig.",
            "es": "Estoy tomando medicamentos. Por favor, tenga cuidado.", "ja": "薬を服用しています。気をつけてください。",
            "zh": "我正在服药，请小心。", "ko": "저는 약을 복용 중이에요. 조심해 주세요.",
            "ar": "أنا أتناول دواءً. يرجى الحذر.",
        },
        "high_fever": {
            "en": "I have a high fever.", "hi": "मुझे तेज़ बुखार है।", "fr": "J'ai une forte fièvre.",
            "de": "Ich habe hohes Fieber.", "es": "Tengo mucha fiebre.", "ja": "高熱があります。",
            "zh": "我发高烧。", "ko": "고열이 있어요.", "ar": "لدي حمى شديدة.",
        },
        "chest_pain": {
            "en": "I have chest pain. Please help me.", "hi": "मुझे सीने में दर्द है। कृपया मेरी मदद करें।",
            "fr": "J'ai une douleur à la poitrine. Aidez-moi, s'il vous plaît.",
            "de": "Ich habe Brustschmerzen. Bitte helfen Sie mir.",
            "es": "Tengo dolor en el pecho. Por favor, ayúdeme.", "ja": "胸が痛みます。助けてください。",
            "zh": "我胸口疼，请帮帮我。", "ko": "가슴이 아파요. 도와주세요.", "ar": "أشعر بألم في الصدر. أرجو مساعدتي.",
        },
        "diabetic": {
            "en": "I am diabetic.", "hi": "मुझे मधुमेह (डायबिटीज़) है।", "fr": "Je suis diabétique.",
            "de": "Ich bin Diabetiker(in).", "es": "Soy diabético/a.", "ja": "私は糖尿病です。",
            "zh": "我有糖尿病。", "ko": "저는 당뇨병이 있어요.", "ar": "أنا مصاب بمرض السكري.",
        },
    },
    "taxi": {
        "take_me_here": {
            "en": "Please take me to this address.",
            "hi": "कृपया मुझे इस पते पर ले चलें। (Kripya mujhe is pate par le chalein.)",
            "fr": "Veuillez m'emmener à cette adresse.", "de": "Bitte bringen Sie mich zu dieser Adresse.",
            "es": "Por favor, lléveme a esta dirección.", "ja": "この住所まで連れて行ってください。",
            "zh": "请带我去这个地址。", "ko": "이 주소로 데려다 주세요.",
            "ar": "من فضلك خذني إلى هذا العنوان.",
        },
        "use_meter": {
            "en": "Please use the meter.", "hi": "कृपया मीटर का उपयोग करें। (Kripya meter ka upyog karein.)",
            "fr": "Veuillez utiliser le compteur.", "de": "Bitte benutzen Sie das Taxameter.",
            "es": "Por favor, use el taxímetro.", "ja": "メーターを使ってください。",
            "zh": "请使用计价器。", "ko": "미터기를 사용해 주세요.", "ar": "من فضلك استخدم العداد.",
        },
        "stop_here": {
            "en": "Please stop here.", "hi": "कृपया यहाँ रोकें। (Kripya yahan rokein.)",
            "fr": "Veuillez vous arrêter ici.", "de": "Bitte halten Sie hier an.",
            "es": "Por favor, deténgase aquí.", "ja": "ここで止めてください。",
            "zh": "请在这里停车。", "ko": "여기서 세워 주세요.", "ar": "من فضلك توقف هنا.",
        },
        "wait_here": {
            "en": "Please wait here for me.", "hi": "कृपया यहाँ मेरा इंतज़ार करें। (Kripya yahan mera intezaar karein.)",
            "fr": "Veuillez m'attendre ici.", "de": "Bitte warten Sie hier auf mich.",
            "es": "Por favor, espéreme aquí.", "ja": "ここで待っていてください。",
            "zh": "请在这里等我。", "ko": "여기서 저를 기다려 주세요.", "ar": "من فضلك انتظرني هنا.",
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
    available = target_lang in entry
    text = entry.get(target_lang, entry["en"])
    return {
        "text": text, "demo": not available, "category": category,
        "phrase_id": phrase_id, "lang": target_lang,
    }


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
    available = target_lang in entry
    text = entry.get(target_lang, entry["en"])
    return {"text": text, "demo": not available, "phrase_id": phrase_id, "lang": target_lang}


def _looks_garbled(text: str) -> bool:
    """MyMemory occasionally returns a string of bare '?' characters (seen
    in practice when it mishandles a non-Latin-script SOURCE language) --
    that's a silent failure, not a translation, and must never be shown to
    a tourist as if it were real."""
    stripped = text.replace("?", "").replace(" ", "").strip()
    return not stripped


def _mymemory_translate(text: str, target_lang: str, source_lang: str) -> str | None:
    """Free-tier fallback (no key/signup needed) so real translation works
    out of the box, e.g. for the Two-Way Voice Translator, even before
    anyone configures GOOGLE_TRANSLATE_API_KEY. Returns None (never a
    guess) on any failure, garbled result, or low-confidence match.

    MyMemory is a translation-*memory* lookup, not a pure MT API: its
    top-level `translatedText` is whichever stored entry is most similar to
    the query, which can be a wrong/mismatched human-submitted phrase with
    a deceptively high similarity score (confirmed in testing: "Where is
    the nearest train station?" -> a nonsense stored phrase at match=0.87).
    Its own `matches` list also carries a live neural-MT entry
    (`created-by: "MT!"`) when one exists -- that's the engine's actual
    translation of this exact text, so it's preferred over the memory-match
    ranking whenever present and not garbled."""
    try:
        resp = httpx.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": f"{source_lang}|{target_lang}"},
            timeout=6.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("MyMemory translation request failed: %s", e)
        return None

    for m in data.get("matches") or []:
        candidate = m.get("translation")
        if m.get("created-by") == "MT!" and candidate and not _looks_garbled(candidate):
            return candidate

    response_data = data.get("responseData") or {}
    top = response_data.get("translatedText")
    top_match = response_data.get("match") or 0
    # No live MT entry available -- only trust the memory-match ranking at
    # a near-exact similarity score, where a wrong/mismatched stored phrase
    # is very unlikely.
    if top and top_match >= 0.98 and not _looks_garbled(top) and "MYMEMORY WARNING" not in top.upper():
        return top

    return None


def translate_text(text: str, target_lang: str, source_lang: str | None = None) -> dict:
    """Translate arbitrary free text. Real (Google Cloud Translation) when a
    key is configured; otherwise a real, free, no-key translation (MyMemory)
    -- so features like the Two-Way Voice Translator actually translate out
    of the box. Only if both are unreachable is the text returned unmodified
    and clearly marked `demo: True` -- fabricating a translation would be
    worse than admitting the capability isn't available."""
    src = source_lang or "en"

    if settings.GOOGLE_TRANSLATE_API_KEY:
        try:
            resp = httpx.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": settings.GOOGLE_TRANSLATE_API_KEY},
                json={"q": text, "target": target_lang, "source": src},
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
            logger.warning("Google Translate request failed, falling back: %s", e)

    translated = _mymemory_translate(text, target_lang, src)
    if translated is not None:
        return {"text": translated, "demo": False}

    return {
        "text": text, "demo": True,
        "note": "Live translation is unavailable right now; showing the original text.",
    }
