"""Cultural Etiquette Guide: curated, reviewed tips on common customs a
foreign tourist in India benefits from knowing (greetings, dress, temple
visits, dining, tipping, photography) -- general, well-established travel
knowledge, not a per-location fact that could be wrong for a specific
place. Same honesty rule as services/translation.py: only English and
Hindi are fully reviewed right now, so any other language falls back to
English with `demo: True` rather than a guessed translation.
"""
from __future__ import annotations

_TOPICS: dict[str, dict[str, dict[str, str]]] = {
    "greetings": {
        "en": {
            "title": "Greetings",
            "text": (
                "A common greeting is \"Namaste\" said with palms pressed together at chest "
                "height (like a slight bow) -- it works for everyone, in any region. A "
                "handshake is also fine in cities and business settings. Many Indians, "
                "especially older relatives, touch an elder's feet as a sign of respect -- "
                "you're not expected to do this, just don't be surprised if you see it."
            ),
        },
        "hi": {
            "title": "अभिवादन",
            "text": (
                "एक आम अभिवादन \"नमस्ते\" है, जिसे छाती के सामने दोनों हथेलियाँ जोड़कर कहा जाता है "
                "(हल्के झुकाव के साथ) -- यह किसी भी क्षेत्र में सबके लिए उपयुक्त है। शहरों और व्यावसायिक "
                "माहौल में हाथ मिलाना भी ठीक है। कई भारतीय, विशेष रूप से बड़े रिश्तेदार, सम्मान के "
                "प्रतीक के रूप में बड़ों के पैर छूते हैं -- आपसे ऐसा करने की अपेक्षा नहीं है, बस इसे देखकर "
                "आश्चर्यचकित न हों।"
            ),
        },
    },
    "temples": {
        "en": {
            "title": "Temples & Religious Sites",
            "text": (
                "Remove your shoes before entering a temple, mosque, or gurdwara (leave "
                "them at the designated rack/area). Dress modestly -- shoulders and knees "
                "covered is a safe default. Some temples restrict entry for non-Hindus to "
                "certain inner areas; look for signage or ask staff rather than assuming. "
                "Photography is often restricted inside the main shrine -- check for signs "
                "or ask before taking a picture."
            ),
        },
        "hi": {
            "title": "मंदिर और धार्मिक स्थल",
            "text": (
                "मंदिर, मस्जिद या गुरुद्वारे में प्रवेश करने से पहले अपने जूते उतारें (उन्हें निर्धारित "
                "रैक/स्थान पर रखें)। शालीन कपड़े पहनें -- कंधे और घुटने ढके होना एक सुरक्षित डिफ़ॉल्ट है। "
                "कुछ मंदिर गैर-हिंदुओं के लिए कुछ आंतरिक क्षेत्रों में प्रवेश प्रतिबंधित करते हैं -- मान लेने के "
                "बजाय संकेत देखें या कर्मचारियों से पूछें। मुख्य गर्भगृह के अंदर फोटोग्राफी अक्सर प्रतिबंधित होती "
                "है -- तस्वीर लेने से पहले संकेत देखें या पूछें।"
            ),
        },
    },
    "dress": {
        "en": {
            "title": "Dress Code",
            "text": (
                "Outside of beach resorts, modest clothing is generally appreciated, "
                "especially for women -- covering shoulders and knees avoids unwanted "
                "attention in most towns and all religious sites. Swimwear is fine only at "
                "pools/beaches, not walking around town. Locals dress more formally than "
                "casual Western beachwear even in warm weather."
            ),
        },
        "hi": {
            "title": "पहनावा",
            "text": (
                "समुद्र तट के रिसॉर्ट्स के बाहर, शालीन कपड़े पहनना आमतौर पर पसंद किया जाता है, "
                "विशेष रूप से महिलाओं के लिए -- कंधे और घुटने ढकने से अधिकांश शहरों और सभी धार्मिक "
                "स्थलों पर अवांछित ध्यान से बचा जा सकता है। स्विमवियर केवल पूल/समुद्र तट पर ठीक है, "
                "शहर में घूमते समय नहीं। स्थानीय लोग गर्म मौसम में भी सामान्य पश्चिमी समुद्र तट के कपड़ों "
                "से अधिक औपचारिक कपड़े पहनते हैं।"
            ),
        },
    },
    "dining": {
        "en": {
            "title": "Dining",
            "text": (
                "Eating with your right hand is traditional and still common, especially "
                "at local/street food places -- the left hand is considered unclean for "
                "eating (it's fine to hold a drink or cutlery with it if cutlery is "
                "provided). It's polite to wash your hands before and after a meal, and "
                "many households eat seated on the floor for home meals -- follow your "
                "host's lead."
            ),
        },
        "hi": {
            "title": "भोजन",
            "text": (
                "दाहिने हाथ से खाना पारंपरिक है और अभी भी आम है, खासकर स्थानीय/स्ट्रीट फूड जगहों पर "
                "-- खाने के लिए बायाँ हाथ अशुद्ध माना जाता है (यदि कटलरी दी गई हो तो उससे पेय या कटलरी "
                "पकड़ना ठीक है)। भोजन से पहले और बाद में हाथ धोना शिष्टाचार है, और कई घरों में लोग "
                "फर्श पर बैठकर भोजन करते हैं -- अपने मेज़बान का अनुसरण करें।"
            ),
        },
    },
    "tipping": {
        "en": {
            "title": "Tipping",
            "text": (
                "Tipping isn't mandatory but is appreciated: about 10% at restaurants "
                "(check if a service charge is already added), small notes (₹20-50) for "
                "porters, drivers, or hotel staff for a specific service. Rounding up an "
                "auto-rickshaw/taxi fare is common and welcomed rather than expected."
            ),
        },
        "hi": {
            "title": "टिप देना",
            "text": (
                "टिप देना अनिवार्य नहीं है लेकिन इसकी सराहना की जाती है: रेस्टोरेंट में लगभग 10% "
                "(देखें कि क्या सेवा शुल्क पहले से जोड़ा गया है), किसी विशेष सेवा के लिए पोर्टर, ड्राइवर या "
                "होटल स्टाफ को छोटे नोट (₹20-50)। ऑटो-रिक्शा/टैक्सी का किराया राउंड अप करना आम है "
                "और स्वागत योग्य है, हालांकि अपेक्षित नहीं।"
            ),
        },
    },
    "photography": {
        "en": {
            "title": "Photography",
            "text": (
                "Ask before photographing individuals, especially in villages or at "
                "religious ceremonies -- some people (and most temple interiors) don't "
                "want to be photographed. Military installations, airports, and some "
                "government buildings prohibit photography entirely -- look for posted "
                "signs. Drones require prior permission in most areas."
            ),
        },
        "hi": {
            "title": "फोटोग्राफी",
            "text": (
                "व्यक्तियों की तस्वीर लेने से पहले पूछें, खासकर गाँवों में या धार्मिक समारोहों में -- कुछ "
                "लोग (और अधिकांश मंदिरों के अंदरूनी हिस्से) फोटो नहीं खिंचवाना चाहते। सैन्य प्रतिष्ठान, "
                "हवाई अड्डे और कुछ सरकारी इमारतें फोटोग्राफी को पूरी तरह प्रतिबंधित करती हैं -- लगे संकेतों "
                "को देखें। अधिकांश क्षेत्रों में ड्रोन के लिए पूर्व अनुमति आवश्यक है।"
            ),
        },
    },
}


def list_topics() -> list[str]:
    return sorted(_TOPICS.keys())


def get_topic(topic: str, lang: str) -> dict:
    entry = _TOPICS.get(topic)
    if entry is None:
        return {"title": None, "text": None, "demo": True, "error": f"Unknown etiquette topic: {topic}"}
    available = lang in entry
    content = entry.get(lang, entry["en"])
    return {"title": content["title"], "text": content["text"], "demo": not available, "topic": topic, "lang": lang}
