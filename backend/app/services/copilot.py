"""AI Safety Copilot: a chat-style assistant that translates signals the
platform already computes -- SHAP contributions, dispatch ranking, zone risk,
alert counts -- into plain-English sentences.

Two layers, in this order, and the order is the whole design:

1. An intent router (keyword/regex -> a handler that queries the DB and
   formats a sentence). Everything safety-critical lives here, because a
   tourist asking "where is the nearest hospital?" must get a real row with
   a real distance. A language model must never be the thing that answers
   that -- a plausible-sounding invented hospital is worse than no answer.

2. For everything else, services/llm.py: a real language model (a local
   Ollama model by default -- free, no API key, nothing leaves the machine;
   a cloud key is used instead when one is configured). This is what lets
   the assistant answer open-ended questions -- travel, culture, language,
   "what's this festival about" -- instead of dead-ending on a fixed list.
   It is grounded with the tourist's own live context and instructed to
   defer to layer 1 for anything requiring live platform data.

If no model is available, layer 2 simply doesn't run and the assistant says
what it can do -- the app degrades, it never breaks.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.incident import Incident
from app.models.place import PointOfInterest
from app.models.police import PoliceUnit
from app.models.tourist import Tourist
from app.models.zone import Zone
from app.services import consular, dispatch, llm, maps, translation
from app.services.geo import haversine_m, min_distance_to_route, zones_containing_point
from app.services.safety import band_for, compute_safety_score

_CONTRIBUTION_LABELS = {
    "zone_risk": "entering a higher-risk zone",
    "hour": "the time of day",
    "anomaly_score": "moving faster/differently than their usual pattern",
    "crime_index": "the area's crime index",
    "weather_risk": "current weather conditions",
}


def _find_tourist(db: Session, needle: str) -> Tourist | None:
    needle = needle.strip()
    if needle.isdigit():
        t = db.get(Tourist, int(needle))
        if t:
            return t
    return (
        db.query(Tourist)
        .filter(Tourist.full_name.ilike(f"%{needle}%") | Tourist.digital_id.ilike(f"%{needle}%"))
        .first()
    )


def _explain_sentence(tourist: Tourist, result: dict) -> str:
    contributions = (result["breakdown"].get("explanation") or {}).get("contributions")
    band = result["band"]
    if not contributions:
        return (
            f"{tourist.full_name}'s current safety score is {round(result['score'])} "
            f"({band}). Zone: {result['breakdown']['zone']}, "
            f"crime index {result['breakdown']['crime_index']}."
        )
    # Positive SHAP contribution = pushes score DOWN toward danger. Sorted by
    # magnitude, same "main driver" framing as the roadmap's worked example.
    ranked = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
    parts = []
    for name, value in ranked[:3]:
        if abs(value) < 1:
            continue
        label = _CONTRIBUTION_LABELS.get(name, name)
        # SHAP contributions are on the SAFETY score (higher = safer): a
        # negative contribution pulled the safety score down, i.e. pushed
        # RISK up -- shown here as "+" against risk, matching how an
        # operator reads "what made this worse".
        sign = "+" if value < 0 else "-"
        parts.append(f"{label} ({sign}{abs(round(value))})")
    if not parts:
        return f"{tourist.full_name}'s score ({round(result['score'])}, {band}) is near its baseline -- no single factor dominates."
    driver = ranked[0][0]
    return (
        f"{tourist.full_name}'s risk is {band} (score {round(result['score'])}). "
        f"Main factors: {', '.join(parts)}. "
        f"Primary driver: {_CONTRIBUTION_LABELS.get(driver, driver)}."
    )


def _intent_why_flagged(db: Session, question: str) -> str | None:
    m = re.search(r"(?:why (?:was|is)|explain).*?tourist[s]?\s*#?\s*([\w\-]+)", question, re.I)
    if not m:
        return None
    tourist = _find_tourist(db, m.group(1))
    if not tourist:
        return f"I couldn't find a tourist matching \"{m.group(1)}\"."
    result = compute_safety_score(db, tourist)
    return _explain_sentence(tourist, result)


def _intent_at_risk_list(db: Session, question: str) -> str | None:
    if not re.search(r"(risk|danger|flagged|jumped|dropped).*(tourist|who|which)|which tourist", question, re.I):
        return None
    at_risk = (
        db.query(Tourist)
        .filter(Tourist.safety_score < 50)
        .order_by(Tourist.safety_score.asc())
        .limit(5)
        .all()
    )
    if not at_risk:
        return "No tourists are currently below a safe score -- everyone tracked is at 50+."
    lines = [f"{t.full_name} ({t.digital_id}): {round(t.safety_score)} [{band_for(t.safety_score)}]"
             for t in at_risk]
    return "Tourists currently at elevated risk:\n" + "\n".join(lines)


def _intent_alert_summary(db: Session, question: str) -> str | None:
    if not re.search(r"how many.*alert|alert.*count|active alert", question, re.I):
        return None
    active = db.query(Alert).filter(Alert.acknowledged.is_(False)).count()
    critical = db.query(Alert).filter(
        Alert.acknowledged.is_(False), Alert.severity == "critical"
    ).count()
    return f"There are {active} unacknowledged alerts right now, {critical} of them critical."


def _intent_open_incidents(db: Session, question: str) -> str | None:
    if not re.search(r"open incident|incident.*(open|pending)|how many incident", question, re.I):
        return None
    open_count = db.query(Incident).filter(Incident.status != "resolved").count()
    return f"There are {open_count} open incidents right now."


def _intent_dispatch(db: Session, question: str) -> str | None:
    m = re.search(r"(?:nearest unit|dispatch).*?tourist[s]?\s*#?\s*([\w\-]+)", question, re.I)
    if not m:
        return None
    tourist = _find_tourist(db, m.group(1))
    if not tourist or tourist.last_lat is None:
        return "I don't have a live location for that tourist."
    ranked = dispatch.rank_units(db, tourist.last_lat, tourist.last_lng)
    if not ranked:
        return f"No response units are currently available near {tourist.full_name}."
    top = ranked[0]
    return (
        f"Nearest unit to {tourist.full_name}: {top['name']} ({top['unit_type']}), "
        f"{top['distance_km']} km away, ETA ~{round(top['eta_min'])} min."
    )


_OPERATOR_SYSTEM_PROMPT = """You are an assistant inside the control-room dashboard of a Smart \
Tourist Safety platform used by police and emergency responders in India.

Rules:
- Answer the operator's question helpfully and concisely (1-4 sentences). No markdown, no emoji.
- You do NOT have live access to tourist records, alerts, incidents or unit positions. If the \
question needs live data, say so and tell them to ask "why was tourist <id> flagged?", "which \
tourists are at risk?", "how many active alerts?", "how many open incidents?" or "nearest unit \
to tourist <id>", which the dashboard answers from the database.
- Never invent a tourist, incident, alert, or location.
- You may answer general questions about procedure, safety practice, or how this platform works."""


def answer_operator_question(db: Session, question: str, history: list[Turn] | None = None) -> dict:
    """Control-room side: operational questions about the live situation."""
    for handler in (
        _intent_why_flagged, _intent_dispatch, _intent_at_risk_list,
        _intent_alert_summary, _intent_open_incidents,
    ):
        answer = handler(db, question)
        if answer:
            return {"answer": answer, "handled": True}
    operator_answer = llm.complete(
        _OPERATOR_SYSTEM_PROMPT,
        f"{_format_history(history)}Control-room operator asks: {question.strip()}",
    ) if (question or "").strip() else None
    if operator_answer:
        return {"answer": operator_answer, "handled": True, "source": "llm"}
    return {
        "answer": (
            "I can answer questions like: \"why was tourist 104 flagged?\", "
            "\"which tourists are at risk?\", \"how many active alerts?\", "
            "\"how many open incidents?\", or \"nearest unit to tourist 104\"."
        ),
        "handled": False,
    }


# ---------------------------------------------------------------- tourist side
def _nearest_help(db: Session, tourist: Tourist, unit_types: list[str]) -> str:
    if tourist.last_lat is None:
        return "I don't have your current location yet -- enable tracking first."
    units = db.query(PoliceUnit).filter(PoliceUnit.available.is_(True)).all()
    candidates = [u for u in units if u.unit_type in unit_types] or units
    if not candidates:
        return "No response units are registered nearby right now."
    nearest = min(candidates, key=lambda u: haversine_m(tourist.last_lat, tourist.last_lng, u.lat, u.lng))
    km = round(haversine_m(tourist.last_lat, tourist.last_lng, nearest.lat, nearest.lng) / 1000, 1)
    return f"Nearest {nearest.unit_type}: {nearest.name} at {nearest.station}, about {km} km away. Call {nearest.phone}."


# Each "find me the nearest X" intent needs BOTH a locating verb and the
# thing being located. Without the locating half, "do I need a doctor for a
# mosquito bite?" would be answered with a hospital address instead of the
# question the tourist actually asked -- so those fall through to the
# open-ended model instead.
_LOCATING = r"(?:near(?:est|by)?|close(?:st)?|where|find|show|take me|get me|closest|around here|directions?)"


def _intent_nearest_hospital(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(rf"{_LOCATING}.*\b(hospital|ambulance|emergency room|clinic)\b"
                     rf"|\b(hospital|ambulance|clinic)\b.*{_LOCATING}", question, re.I):
        return None
    return _nearest_help(db, tourist, ["ambulance"])


def _intent_nearest_police(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(rf"{_LOCATING}.*\b(police|cop|officer)\b"
                     rf"|\bpolice\b.*{_LOCATING}", question, re.I):
        return None
    return _nearest_help(db, tourist, ["police"])


def _intent_area_safe(db: Session, tourist: Tourist, question: str) -> str | None:
    # Only claims questions about the tourist's CURRENT surroundings. A
    # broader safety question ("is it safe to travel alone at night as a
    # woman?") is a real question deserving a real answer, not a zone
    # readout, so it goes to the open-ended model instead.
    if not re.search(r"(is|how)\s+(this|the)\s+(area|place|zone|neighbou?rhood)"
                     r"|(am|are)\s+i\s+safe|safe\s+(here|right now|where i am)"
                     r"|(danger|risk)\w*\s+(here|zone|area)"
                     r"|what.{0,20}\b(zone|area)\b.{0,20}(am i|i'?m) in", question, re.I):
        return None
    if tourist.last_lat is None:
        return "I don't have your current location yet -- enable tracking first."
    zones = db.query(Zone).all()
    inside = zones_containing_point(tourist.last_lat, tourist.last_lng, zones)
    band = band_for(tourist.safety_score)
    if not inside:
        return f"You're in an open area with no defined risk zone. Your current safety band is {band}."
    worst = max(inside, key=lambda z: {"low": 0, "medium": 1, "high": 2, "restricted": 3}.get(z.risk_level, 1))
    return (
        f"You're inside \"{worst.name}\" ({worst.risk_level} risk). "
        f"Your current safety band is {band}. "
        + ("Consider moving to a lower-risk area." if worst.risk_level in ("high", "restricted") else "Stay alert but this is generally fine.")
    )


def _intent_advice(db: Session, tourist: Tourist, question: str) -> str | None:
    # Deliberately narrow: only the open-ended "what now?" with no other
    # subject. "help me find a good restaurant" is a real question for the
    # open-ended model, not a prompt for a safety-band platitude.
    if not re.search(r"^\s*(what should i do( now)?|any advice|what do i do)\s*\??\s*$"
                     r"|what should i do (now|next)\b", question.strip(), re.I):
        return None
    band = band_for(tourist.safety_score)
    advice = {
        "safe": "You're in good shape. Keep tracking on and enjoy your trip.",
        "moderate": "Stay aware of your surroundings, stick to your itinerary, and keep your phone charged.",
        "risky": "Consider moving toward a safer area, let your Trip Guardian know where you are, and avoid isolated spots.",
        "danger": "This is a high-risk situation. Move to a populated area now, and use the SOS button if you feel unsafe.",
    }
    return advice.get(band, "Stay alert and keep tracking enabled.")


def _intent_embassy(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"embassy|consulate|my country|my embassy", question, re.I):
        return None
    country_code = consular.normalize_nationality(tourist.nationality_code or tourist.nationality)
    if not country_code or country_code == "IN":
        return "This is an embassy/consulate lookup for foreign tourists -- I don't have one on file for your nationality."
    missions = consular.missions_for(country_code, tourist.last_lat, tourist.last_lng)
    if not missions:
        guidance = consular.guidance_for(country_code)
        return (
            f"I don't have a listed mission for your nationality yet. Your registered "
            f"helpline language is {guidance['helpline_language']} -- the 24x7 tourist "
            f"helpline (1363) can support you in that language, or call 112 for emergencies."
        )
    m = missions[0]
    distance = f", about {m['distance_km']} km away" if "distance_km" in m else ""
    return f"Nearest {m['mission_type']}: {m['country_name']} {m['mission_type']} in {m['city']}{distance}. Call {m['phone']}."


def _intent_why_flagged_self(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"why (was|is) (i|my risk|my score)|why flagged|why am i", question, re.I):
        return None
    result = compute_safety_score(db, tourist)
    return _explain_sentence(tourist, result)


# ---------------------------------------------------------------- itinerary-aware
def _itinerary(tourist: Tourist) -> list[dict]:
    try:
        return json.loads(tourist.itinerary or "[]")
    except (TypeError, ValueError):
        return []


def _intent_next_destination(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"next (destination|stop|place)|where.*(going|next)|what'?s next", question, re.I):
        return None
    stops = _itinerary(tourist)
    if not stops:
        return "You don't have a saved itinerary yet -- upload one from the Plan tab and I can guide you stop by stop."
    nxt = stops[0]
    if tourist.last_lat is None:
        return f"Your next planned destination is {nxt['name']}. Enable location tracking and I can tell you how far that is."
    route = maps.directions(tourist.last_lat, tourist.last_lng, nxt["lat"], nxt["lng"])
    eta = round(route["duration_min"])
    demo_note = " (estimated)" if route["demo"] else ""
    return f"Your next planned destination is {nxt['name']}. It's approximately {eta} minutes away{demo_note}."


def _intent_show_itinerary(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"show.*itinerary|my itinerary|my (trip|travel) plan|my schedule", question, re.I):
        return None
    stops = _itinerary(tourist)
    if not stops:
        return "You don't have a saved itinerary yet -- upload one from the Plan tab."
    lines = [f"{i + 1}. {s['name']}" for i, s in enumerate(stops)]
    return "Your itinerary:\n" + "\n".join(lines)


def _intent_on_route(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"on (the )?(correct |right )?route|on track|following.*route|am i lost", question, re.I):
        return None
    stops = _itinerary(tourist)
    if not stops or tourist.last_lat is None:
        return "I don't have enough information (itinerary + live location) to check your route yet."
    deviation_m = min_distance_to_route(tourist.last_lat, tourist.last_lng, stops)
    if deviation_m <= settings.ROUTE_DEVIATION_THRESHOLD_M:
        return "You're on your planned route -- everything looks normal."
    km = round(deviation_m / 1000, 1)
    return (
        f"You appear to be about {km} km from your planned route. This may just be a "
        f"change of plans -- would you like navigation back to {stops[0]['name']}?"
    )


_TRANSPORT_WORDS = r"(?:transport|bus stop|bus|metro|taxi|cab|auto[\s-]?rickshaw|railway|train station)"


def _intent_nearest_transport(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(rf"{_LOCATING}.*{_TRANSPORT_WORDS}|{_TRANSPORT_WORDS}.*{_LOCATING}"
                     rf"|\bbook (?:a |me a )?(?:cab|taxi|auto)\b", question, re.I):
        return None
    if tourist.last_lat is None:
        return "I don't have your current location yet -- enable tracking first."
    category = None
    if re.search(r"metro", question, re.I):
        category = "metro_station"
    elif re.search(r"bus", question, re.I):
        category = "bus_stop"
    elif re.search(r"rail|train", question, re.I):
        category = "railway_station"
    elif re.search(r"taxi|cab|auto", question, re.I):
        category = "taxi_stand"
    q = db.query(PointOfInterest)
    if category:
        q = q.filter(PointOfInterest.category == category)
    else:
        q = q.filter(PointOfInterest.category.in_(
            ["bus_stop", "metro_station", "railway_station", "taxi_stand"]))
    places = q.all()
    if not places:
        return "I don't have any transport options registered nearby yet."
    nearest = min(places, key=lambda p: haversine_m(tourist.last_lat, tourist.last_lng, p.lat, p.lng))
    km = round(haversine_m(tourist.last_lat, tourist.last_lng, nearest.lat, nearest.lng) / 1000, 1)
    return f"Nearest {nearest.category.replace('_', ' ')}: {nearest.name}, about {km} km away."


def _intent_nearest_pharmacy(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(rf"{_LOCATING}.*\b(pharmacy|chemist|medical store|drug ?store)\b"
                     rf"|\b(pharmacy|chemist|medical store|drug ?store)\b.*{_LOCATING}",
                     question, re.I):
        return None
    if tourist.last_lat is None:
        return "I don't have your current location yet -- enable tracking first."
    places = db.query(PointOfInterest).filter(PointOfInterest.category == "pharmacy").all()
    if not places:
        return "I don't have any pharmacies registered nearby yet."
    nearest = min(places, key=lambda p: haversine_m(tourist.last_lat, tourist.last_lng, p.lat, p.lng))
    km = round(haversine_m(tourist.last_lat, tourist.last_lng, nearest.lat, nearest.lng) / 1000, 1)
    phone = f" ☎ {nearest.phone}" if nearest.phone else ""
    return f"Nearest pharmacy: {nearest.name}, about {km} km away.{phone}"


def _intent_go_to_hotel(db: Session, tourist: Tourist, question: str) -> str | None:
    """"Take me to my hotel" / "where is my hotel" -- routes to the hotel
    already on the tourist's record, geocoded on demand (services/maps.py).
    Never invents a hotel or a location for one it can't place."""
    if not re.search(r"\bhotel\b|where.*(i|we).*(stay|staying)|back to my (room|stay|accommodation)", question, re.I):
        return None
    if not (tourist.hotel or "").strip():
        return "I don't have a hotel saved on your profile yet -- add it in the Me tab and I can guide you back to it."
    if tourist.last_lat is None:
        return f"Your hotel on file is {tourist.hotel}. Enable location tracking and I can tell you how far away it is."
    located = maps.geocode(tourist.hotel)
    if not located:
        return (
            f"Your hotel on file is {tourist.hotel}, but I couldn't place it on the map. "
            f"Try adding the city to the hotel name in the Me tab."
        )
    route = maps.directions(tourist.last_lat, tourist.last_lng, located["lat"], located["lng"])
    eta = round(route["duration_min"])
    demo_note = " (estimated)" if route["demo"] else ""
    return (
        f"{tourist.hotel} is about {route['distance_km']} km away, roughly {eta} minutes{demo_note}. "
        f"Open Navigation on the Plan tab for turn-by-turn voice guidance."
    )


# "translate X to Hindi" / "how do I say X in French" -- the phrase and the
# target language are pulled out of whatever the tourist actually said,
# rather than matching a fixed set of sentences.
_TRANSLATE_PATTERNS = [
    r"translate\s+(?:this\s+)?[\"']?(?P<text>.+?)[\"']?\s+(?:in|into|to)\s+(?P<lang>[a-z]+)\s*$",
    r"how (?:do|can) i say\s+[\"']?(?P<text>.+?)[\"']?\s+in\s+(?P<lang>[a-z]+)\s*$",
    r"(?:say|what'?s)\s+[\"']?(?P<text>.+?)[\"']?\s+in\s+(?P<lang>[a-z]+)\s*$",
]


def _intent_translate(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"translate|how do i say|how can i say|in (hindi|french|german|spanish|japanese|chinese|korean|arabic)", question, re.I):
        return None

    for pattern in _TRANSLATE_PATTERNS:
        m = re.search(pattern, question.strip(), re.I)
        if not m:
            continue
        phrase = m.group("text").strip()
        lang_name = m.group("lang").strip().lower()
        code = next(
            (c for c, name in translation.SUPPORTED_LANGUAGES.items() if name.lower() == lang_name),
            None,
        )
        if not code:
            # A language the curated phrasebook doesn't cover (Assamese,
            # Thai, ...). Fall through to the open-ended model, which may
            # well know it, rather than refusing with a list.
            return None
        result = translation.translate_text(phrase, code)
        if result.get("demo"):
            return (
                f"Live translation isn't configured in this deployment, so I can't translate "
                f"\"{phrase}\" reliably. The Translate card on the Help tab has ready-made "
                f"emergency phrases in {translation.SUPPORTED_LANGUAGES[code]} that are always available."
            )
        return f"In {translation.SUPPORTED_LANGUAGES[code]}: {result['text']}"

    if re.search(r"^\s*translate( this| that)?\s*[.?!]?\s*$", question.strip(), re.I):
        supported = ", ".join(translation.SUPPORTED_LANGUAGES.values())
        return (
            "Tell me what to translate and into which language -- for example, "
            "\"translate I need a doctor into Hindi\". I support: " + supported + "."
        )
    # Some other translation-shaped question we couldn't parse -- let the
    # open-ended model try rather than dead-ending.
    return None


def _intent_emergency_procedure(db: Session, tourist: Tourist, question: str) -> str | None:
    """"What should I do in an emergency?" -- procedure guidance, distinct
    from _intent_emergency_call (which is about contacting help right now)
    and from _intent_advice (which is about the current risk band)."""
    if not re.search(r"(what|how).*(do|to do|should i).*(emergency|danger|trouble|attacked|robbed|lost)"
                     r"|emergency (procedure|steps|advice|guidance)|in an emergency", question, re.I):
        return None
    contacts = "your saved emergency contacts"
    return (
        "In an emergency: 1) Press the 🆘 SOS button -- it alerts responders and "
        f"{contacts} with your live location. 2) Call 112, India's all-in-one emergency "
        "number (1363 for the tourist helpline). 3) Move somewhere public and well-lit if "
        "you can. 4) Keep location tracking on so responders can find you. If you're being "
        "forced to act against your will, use your duress PIN instead of the normal unlock."
    )


def _intent_emergency_call(db: Session, tourist: Tourist, question: str) -> str | None:
    if not re.search(r"call (emergency|police|ambulance|help)|emergency (call|number|services)", question, re.I):
        return None
    # Deliberately never triggers a real SOS from chat text -- an emergency
    # is raised through the explicit SOS button/duress PIN, never inferred
    # from a typed sentence that could be a false positive.
    return (
        "For a real emergency, please use the 🆘 SOS button so I can notify responders and "
        "your emergency contacts immediately. India's all-in-one emergency number is 112."
    )


Turn = tuple[str, str]  # (role, text) -- "user" | "assistant"

# A short affirmation on its own ("yes", "yes yes", "sure", "go ahead", ...)
# carries no meaning without the assistant's previous turn. Matched against
# the FULL stripped message so a real question that happens to start with
# "yes" (rare, but "yes but where is the pharmacy" is a real question) isn't
# swallowed.
_AFFIRMATION_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok(?:ay)?|please|go ahead|do it|please do|"
    r"(?:yes[,.\s]*)+)[.!\s]*$",
    re.I,
)

# When the assistant's last reply *offered* to look something up, a bare
# "yes" should resolve to that real lookup (through the same intent handlers
# below -- a real distance/name, never the LLM guessing one) rather than
# dead-ending on "I'm not sure what you're asking". Ordered most-specific
# first where offers could overlop (e.g. "transport" before "hotel").
_FOLLOWUP_OFFERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"transport|taxi|cab|bus|metro|railway|train station", re.I), "find nearest transport"),
    (re.compile(r"hospital|ambulance|clinic", re.I), "nearest hospital"),
    (re.compile(r"pharmacy|chemist|medical store", re.I), "nearest pharmacy"),
    (re.compile(r"police station|police officer|\bpolice\b", re.I), "nearest police station"),
    (re.compile(r"\bhotel\b|your (?:stay|accommodation)", re.I), "take me to my hotel"),
    (re.compile(r"route|navigation|on track", re.I), "am I on the correct route"),
    (re.compile(r"itinerary|travel plan|schedule", re.I), "show my itinerary"),
    (re.compile(r"embassy|consulate", re.I), "my embassy"),
]


def resolve_followup(question: str, history: list[Turn]) -> str:
    """Rewrite a bare affirmation ("yes yes") into the concrete question it's
    affirming, read off the assistant's own last offer -- so it's answered by
    the same real-data intent handler the original offer promised, instead of
    the LLM inventing a distance/name it doesn't actually have. Returns
    `question` unchanged when there's nothing to resolve (not an affirmation,
    no history, or the last offer didn't name anything this app can look
    up) -- callers still fall through to the open-ended model in that case."""
    if not history or not _AFFIRMATION_RE.match(question.strip()):
        return question
    last_assistant = next((text for role, text in reversed(history) if role == "assistant"), None)
    if not last_assistant:
        return question
    for pattern, canonical in _FOLLOWUP_OFFERS:
        if pattern.search(last_assistant):
            return canonical
    return question


def answer_tourist_question(
    db: Session, tourist: Tourist, question: str, history: list[Turn] | None = None,
) -> dict:
    """Tourist side: nearest help, area safety, itinerary-aware guidance."""
    history = history or []
    question = resolve_followup(question, history)
    for handler in (
        # Order matters where keyword sets overlap:
        #  - translate first: "how do I say I need a doctor in Hindi" would
        #    otherwise be caught by the hospital intent's "doctor".
        #  - emergency procedure before the generic advice intent, which
        #    also matches "what should I do".
        #  - pharmacy before hospital: "medical store" would otherwise match
        #    hospital's broader "medical" keyword.
        #  - transport before hotel: "find a cab to my hotel" is a transport
        #    request first.
        _intent_translate, _intent_emergency_procedure, _intent_emergency_call,
        _intent_nearest_pharmacy, _intent_nearest_hospital,
        _intent_nearest_police, _intent_nearest_transport, _intent_go_to_hotel,
        _intent_next_destination, _intent_show_itinerary, _intent_on_route,
        _intent_area_safe, _intent_embassy, _intent_why_flagged_self, _intent_advice,
    ):
        answer = handler(db, tourist, question)
        if answer:
            return {"answer": answer, "handled": True}

    # No deterministic handler matched. Hand the question to a real language
    # model, grounded in this tourist's live context AND the recent
    # conversation, so the assistant can answer anything -- not just the
    # intents above, and without losing the thread on a genuine follow-up
    # resolve_followup's keyword list didn't happen to cover. Only if no
    # model is available at all do we fall back to describing what we can do.
    llm_answer = _llm_answer(db, tourist, question, history)
    if llm_answer:
        return {"answer": llm_answer, "handled": True, "source": "llm"}
    return {"answer": _unmatched_reply(question), "handled": False}


def _tourist_context(db: Session, tourist: Tourist) -> str:
    """Real, current facts about this tourist for the model to ground its
    answer in. Only what the assistant already shows the tourist about
    themselves -- no other tourist's data ever enters this prompt."""
    lines = [f"Tourist name: {tourist.full_name}"]
    if tourist.nationality:
        lines.append(f"Nationality: {tourist.nationality}")
    if tourist.last_lat is not None:
        lines.append(f"Current coordinates: {round(tourist.last_lat, 4)}, {round(tourist.last_lng, 4)}")
        zones = db.query(Zone).all()
        inside = zones_containing_point(tourist.last_lat, tourist.last_lng, zones)
        if inside:
            lines.append("Currently inside zone(s): " + ", ".join(
                f"{z.name} ({z.risk_level} risk)" for z in inside))
    else:
        lines.append("Current location: unknown (tracking is off)")
    if tourist.safety_score is not None:
        lines.append(f"Safety score: {round(tourist.safety_score)} ({band_for(tourist.safety_score)})")
    if (tourist.hotel or "").strip():
        lines.append(f"Hotel: {tourist.hotel}")
    stops = _itinerary(tourist)
    if stops:
        lines.append("Itinerary stops (in order): " + ", ".join(s.get("name", "?") for s in stops))
    else:
        lines.append("Itinerary: none saved yet")
    return "\n".join(lines)


_SYSTEM_PROMPT = """You are the voice safety assistant inside MUSAFIR, a smart tourist safety app used by \
travellers in India. You are talking directly to the tourist described below, usually out loud.

Rules:
- Answer the tourist's actual question helpfully and conversationally.
- Be brief: 1-3 short sentences, since your reply is read aloud. No markdown, no lists, no emoji.
- Use the tourist's context below when it is relevant, but you may also answer general travel, \
culture, language, food, transport, weather and safety questions from your own knowledge.
- Never invent specific facts about this app's data: you do NOT know real-time hospital names, \
distances, police unit locations, or their exact route. If asked for those, tell them to ask for \
"nearest hospital", "nearest police station", "find transport" or "am I on the correct route", \
which the app answers from live data.
- For a real emergency, tell them to press the SOS button in the app; India's emergency number \
is 112 and the tourist helpline is 1363. Never claim you have alerted anyone yourself.
- If you genuinely do not know, say so plainly."""


def _format_history(history: list[Turn] | None) -> str:
    if not history:
        return ""
    lines = [f"{'Tourist' if role == 'user' else 'Assistant'}: {text}" for role, text in history]
    return "Recent conversation (most recent last):\n" + "\n".join(lines) + "\n\n"


def _llm_answer(db: Session, tourist: Tourist, question: str, history: list[Turn] | None = None) -> str | None:
    """Open-ended answer from a language model, or None if none is
    configured/reachable (see services/llm.py). Includes the recent
    conversation (if any) so a genuine follow-up -- "what about at night?",
    "why is that?" -- is answered in context instead of as a fresh, unrelated
    question; resolve_followup already handles the narrower case of a bare
    "yes" affirming a real-data offer before this is ever reached."""
    if not (question or "").strip():
        return None
    prompt = (
        f"Tourist's context:\n{_tourist_context(db, tourist)}\n\n"
        f"{_format_history(history)}"
        f"Tourist asks: {question.strip()}"
    )
    return llm.complete(_SYSTEM_PROMPT, prompt)


_CAPABILITY_LIST = (
    "nearest hospital, pharmacy or police station; find transport or a cab; take me to my "
    "hotel; my next destination; show my itinerary; am I on the correct route; is this area "
    "safe; translate a phrase; my embassy; why was I flagged; and what to do in an emergency"
)


def _unmatched_reply(question: str) -> str:
    """A question we have no handler for. Reflect back what was heard (so a
    mis-heard voice command is obvious to the tourist rather than silently
    answered wrong) and list what this assistant can actually do -- never
    guess at an answer for a safety tool."""
    heard = " ".join((question or "").split())[:120]
    if not heard:
        return f"I didn't catch that. I can help with: {_CAPABILITY_LIST}."
    return (
        f"I heard \"{heard}\", but I don't have a way to answer that yet. "
        f"I can help with: {_CAPABILITY_LIST}."
    )


# ---- Pre-login / public assistant -----------------------------------------
# Used by the voice assistant on the Login/Register screens, before we know
# who is asking. Deliberately the narrowest surface in this file: no tourist
# row, no DB query, nothing personal ever enters this prompt -- it can only
# describe the app and point the user at the right real action (log in,
# register, forgot password, or call a real emergency number). Login,
# registration and SOS themselves are never performed here; the frontend's
# voice assistant carries those out through the actual auth/SOS APIs and
# only ever calls this endpoint for open-ended "how does this work" style
# questions. See frontend/src/components/LoginVoiceAssistant.jsx.
_PUBLIC_SYSTEM_PROMPT = """You are the voice assistant on the sign-in screen of MUSAFIR, a tourist \
safety app used in India, talking to someone who has not signed in yet -- possibly a blind or \
low-vision traveller relying entirely on your spoken answer.

Rules:
- Answer only general questions about what MUSAFIR is and how it works (digital tourist ID, \
live safety score, geofencing, one-tap SOS, nearby help, multilingual support).
- Be brief: 1-3 short sentences, since your reply is read aloud. No markdown, no lists, no emoji.
- You know nothing about any specific person -- you have no tourist data, no account information, \
and cannot look anything up. Never invent a name, ID, location or status for anyone.
- If asked to log in, register, recover a password, or for real emergency help, tell them the \
app will do that directly by voice or through the visible form -- you don't perform it yourself.
- India's all-in-one emergency number is 112; the tourist helpline is 1363. Give these if asked, \
but make clear a real SOS in this app requires being signed in first, since it shares live \
location with a real responder.
- If you genuinely do not know, say so plainly."""

_PUBLIC_CAPABILITY_REPLY = (
    "MUSAFIR is a tourist safety app: a digital tourist ID, a live safety score, geofenced risk "
    "alerts, and a one-tap SOS that shares your location with a real responder. Say \"log in\", "
    "\"register\", \"I forgot my password\", or \"emergency\" and I'll take you there. In a real "
    "emergency right now, India's all-in-one number is 112, and the tourist helpline is 1363."
)


def answer_public_question(question: str) -> dict:
    """Pre-login assistant: general app questions only, answered by a real
    language model when one is configured. No database access, no personal
    data -- see the module docstring above `_PUBLIC_SYSTEM_PROMPT`."""
    question = (question or "").strip()
    if not question:
        return {"answer": _PUBLIC_CAPABILITY_REPLY, "handled": False}
    answer = llm.complete(_PUBLIC_SYSTEM_PROMPT, question)
    if answer:
        return {"answer": answer, "handled": True, "source": "llm"}
    # No model configured/reachable: degrade to a real, honest description
    # of what the app can do, never a fabricated answer.
    return {"answer": _PUBLIC_CAPABILITY_REPLY, "handled": False}
