"""CAP 1.2 XML parser (app/services/cap.py)."""
from pathlib import Path

import pytest

from app.services.cap import parse_cap_feed

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parses_a_single_alert_document():
    alerts = parse_cap_feed(_load("sachet_sample.xml"))
    assert len(alerts) == 1
    a = alerts[0]
    assert a["external_id"] == "IN-NDMA-2026-000123"
    assert a["hazard_type"] == "flood"
    assert a["severity"] == "high"  # CAP "Severe" -> this app's "high"
    assert a["area_desc"] == "Kamrup Metropolitan, Assam"
    assert "Flash flood" not in ""  # sanity no-op, message check below
    assert a["message"].startswith("Heavy rainfall")
    assert a["effective"] == "2026-09-01T06:00:00+05:30"
    assert a["expires"] == "2026-09-01T18:00:00+05:30"


def test_parses_the_polygon_and_drops_the_closing_duplicate_point():
    alerts = parse_cap_feed(_load("sachet_sample.xml"))
    polygon = alerts[0]["polygon"]
    assert len(polygon) == 4  # 5 pairs in the fixture, ring-closing point dropped
    assert polygon[0] == [26.10, 91.65]


def test_parses_a_multi_alert_feed_document():
    alerts = parse_cap_feed(_load("sachet_multi_sample.xml"))
    assert len(alerts) == 2
    assert alerts[0]["hazard_type"] == "landslide"
    assert alerts[1]["hazard_type"] == "storm"


def test_severity_mapping():
    alerts = parse_cap_feed(_load("sachet_multi_sample.xml"))
    assert alerts[0]["severity"] == "medium"  # Moderate
    assert alerts[1]["severity"] == "critical"  # Extreme


def test_alert_with_no_area_polygon_still_parses():
    alerts = parse_cap_feed(_load("sachet_multi_sample.xml"))
    assert alerts[1]["polygon"] is None
    assert alerts[1]["area_desc"] == "Regional"


def test_unrecognised_event_text_falls_back_to_storm():
    xml = b"""<?xml version="1.0"?>
    <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <identifier>X-1</identifier>
      <info>
        <event>Something Unusual</event>
        <severity>Minor</severity>
        <description>An unusual event.</description>
      </info>
    </alert>"""
    alerts = parse_cap_feed(xml)
    assert alerts[0]["hazard_type"] == "storm"
    assert alerts[0]["severity"] == "low"


def test_alert_missing_info_block_is_skipped_not_fatal():
    xml = b"""<?xml version="1.0"?>
    <alerts xmlns="urn:oasis:names:tc:emergency:cap:1.2">
      <alert><identifier>bad-1</identifier></alert>
      <alert>
        <identifier>good-1</identifier>
        <info><event>Flood</event><severity>Minor</severity><description>ok</description></info>
      </alert>
    </alerts>"""
    alerts = parse_cap_feed(xml)
    assert len(alerts) == 1
    assert alerts[0]["external_id"] == "good-1"


def test_malformed_xml_raises_rather_than_silently_returning_nothing():
    from xml.etree.ElementTree import ParseError

    from defusedxml.common import DefusedXmlException

    with pytest.raises((ParseError, DefusedXmlException)):
        parse_cap_feed(b"this is not xml at all <<<")


def test_empty_feed_document_returns_empty_list():
    xml = b'<alerts xmlns="urn:oasis:names:tc:emergency:cap:1.2"></alerts>'
    assert parse_cap_feed(xml) == []
