"""Common Alerting Protocol (CAP) 1.2 XML parser.

CAP is the standard India's NDMA SACHET portal, IMD, and most national
disaster-alert authorities publish under -- this parser is generic to the
standard, not tied to one provider's endpoint. See services/disaster.py for
where this plugs into the app (behind DISASTER_FEED_URL, with the existing
simulator as fallback via services/feeds.py) and the module docstring there
for why no specific provider endpoint is hardcoded as the default: SACHET's
underlying feed is served by a JS single-page app with no documented public
XML/JSON endpoint discoverable without provider cooperation, so this is
built to be pointed at any CAP 1.2 source an operator configures, real or a
sandboxed test feed.

Uses defusedxml, not the stdlib's ElementTree, because parsing third-party
XML with the stdlib parser is an XXE/billion-laughs exposure -- this feed
comes from the network by design.
"""
from __future__ import annotations

from defusedxml import ElementTree as DET

_CAP_NS = "{urn:oasis:names:tc:emergency:cap:1.2}"

# CAP's free-text <event> field mapped to this app's four hazard types.
# Anything not matched falls back to "storm" as the most general severe-
# weather bucket rather than being silently dropped.
_EVENT_KEYWORDS = {
    "flood": "flood",
    "landslide": "landslide",
    "earthquake": "earthquake",
    "seismic": "earthquake",
    "cyclone": "storm",
    "storm": "storm",
    "wind": "storm",
    "tsunami": "flood",
}

_SEVERITY_MAP = {
    "extreme": "critical",
    "severe": "high",
    "moderate": "medium",
    "minor": "low",
}


def _tag(el, name: str) -> str | None:
    child = el.find(f"{_CAP_NS}{name}")
    return child.text.strip() if child is not None and child.text else None


def _hazard_type_for(event_text: str) -> str:
    lowered = (event_text or "").lower()
    for keyword, hazard in _EVENT_KEYWORDS.items():
        if keyword in lowered:
            return hazard
    return "storm"


def _parse_polygon(area_el) -> list[list[float]] | None:
    """CAP <polygon> is a space-separated list of "lat,lon" pairs, first
    point repeated last to close the ring -- drop the closing duplicate."""
    polygon_el = area_el.find(f"{_CAP_NS}polygon")
    if polygon_el is None or not polygon_el.text:
        return None
    points = []
    for pair in polygon_el.text.strip().split():
        try:
            lat_str, lng_str = pair.split(",")
            points.append([float(lat_str), float(lng_str)])
        except ValueError:
            continue
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    return points or None


def parse_cap_feed(xml_bytes: bytes) -> list[dict]:
    """Parse a CAP 1.2 <alert> or <alerts>/<feed> document into a list of
    normalised advisory candidates:
        {hazard_type, severity, area_desc, polygon, message, external_id,
         effective, expires}
    Malformed individual <alert> elements are skipped, not fatal to the
    whole feed -- one bad entry from an upstream provider must not drop
    every other real advisory.
    """
    root = DET.fromstring(xml_bytes)

    # A feed document wraps multiple <alert> elements; a single-alert
    # document IS the <alert> root itself.
    alert_els = (
        [root] if root.tag == f"{_CAP_NS}alert" else root.findall(f".//{_CAP_NS}alert")
    )

    out = []
    for alert_el in alert_els:
        try:
            identifier = _tag(alert_el, "identifier")
            info_el = alert_el.find(f"{_CAP_NS}info")
            if info_el is None:
                continue

            event = _tag(info_el, "event") or ""
            severity_raw = (_tag(info_el, "severity") or "moderate").lower()
            description = _tag(info_el, "description") or _tag(info_el, "headline") or event
            effective = _tag(info_el, "effective") or _tag(info_el, "onset")
            expires = _tag(info_el, "expires")

            area_el = info_el.find(f"{_CAP_NS}area")
            area_desc = _tag(area_el, "areaDesc") if area_el is not None else None
            polygon = _parse_polygon(area_el) if area_el is not None else None

            out.append({
                "external_id": identifier,
                "hazard_type": _hazard_type_for(event),
                "severity": _SEVERITY_MAP.get(severity_raw, "medium"),
                "area_desc": area_desc,
                "polygon": polygon,
                "message": description,
                "effective": effective,
                "expires": expires,
            })
        except Exception:  # noqa: BLE001 -- one malformed <alert> must not drop the feed
            continue

    return out
