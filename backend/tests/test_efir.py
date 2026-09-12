"""E-FIR filing, PDF rendering, and its tie-in to the tourist's hash chain."""
import io

import pytest

from app.models.efir import EFIR
from app.models.tourist import IdBlock
from app.services import hashchain
from app.services.efir_pdf import compute_document_hash, render_efir_pdf
from tests.conftest import make_tourist


def _mark_missing(client, admin_headers, tourist_id):
    r = client.post(f"/api/tourists/{tourist_id}/mark-missing", headers=admin_headers)
    assert r.status_code == 200
    return r.json()


def test_mark_missing_files_an_efir(client, admin_headers, db):
    t = make_tourist(db, name="Lost Person")
    body = _mark_missing(client, admin_headers, t.id)

    efir = db.get(EFIR, body["efir_id"])
    assert efir.status == "filed"
    assert efir.tourist_id == t.id
    assert efir.fir_number == body["fir_number"]
    assert efir.document_hash


def test_fir_number_is_unique_per_incident(client, admin_headers, db):
    """A tourist reported missing twice must get two distinct filed reports."""
    t = make_tourist(db)
    first = _mark_missing(client, admin_headers, t.id)
    second = _mark_missing(client, admin_headers, t.id)
    assert first["fir_number"] != second["fir_number"]
    assert first["efir_id"] != second["efir_id"]


def test_filing_appends_an_efir_filed_block_to_the_chain(client, admin_headers, db):
    t = make_tourist(db)
    body = _mark_missing(client, admin_headers, t.id)

    chain = client.get(f"/api/tourists/{t.id}/chain", headers=admin_headers).json()
    assert chain[-1]["event"] == "EFIR_FILED"
    assert body["fir_number"] in chain[-1]["data"]


def test_chain_still_verifies_after_filing(client, admin_headers, db):
    t = make_tourist(db)
    _mark_missing(client, admin_headers, t.id)
    r = client.get(f"/api/tourists/{t.id}/chain/verify", headers=admin_headers)
    assert r.json()["valid"] is True


def test_tampering_the_efir_block_is_detected(client, admin_headers, db):
    """The filed report is only as trustworthy as the chain entry that pins it --
    editing that block after the fact must be caught like any other tamper."""
    t = make_tourist(db)
    _mark_missing(client, admin_headers, t.id)

    block = db.query(IdBlock).filter_by(tourist_id=t.id).order_by(IdBlock.index.desc()).first()
    assert block.event == "EFIR_FILED"
    block.data = '{"fir_number": "FORGED"}'
    db.commit()

    assert hashchain.verify_chain(db, t.id)["valid"] is False


def test_get_efir_by_id(client, admin_headers, db):
    t = make_tourist(db)
    body = _mark_missing(client, admin_headers, t.id)

    r = client.get(f"/api/efirs/{body['efir_id']}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "filed"


def test_get_unknown_efir_404s(client, admin_headers):
    assert client.get("/api/efirs/9999", headers=admin_headers).status_code == 404


def test_efir_pdf_download(client, admin_headers, db):
    t = make_tourist(db)
    body = _mark_missing(client, admin_headers, t.id)

    r = client.get(f"/api/efirs/{body['efir_id']}/pdf", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000


def test_close_efir(client, admin_headers, db):
    t = make_tourist(db)
    body = _mark_missing(client, admin_headers, t.id)
    eid = body["efir_id"]

    r = client.post(f"/api/efirs/{eid}/close", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
    assert r.json()["closed_at"] is not None


def test_closing_twice_rejected(client, admin_headers, db):
    t = make_tourist(db)
    eid = _mark_missing(client, admin_headers, t.id)["efir_id"]
    client.post(f"/api/efirs/{eid}/close", headers=admin_headers)
    assert client.post(f"/api/efirs/{eid}/close", headers=admin_headers).status_code == 400


def test_list_efirs(client, admin_headers, db):
    make_tourist(db, name="A")
    make_tourist(db, name="B")
    tourists = client.get("/api/tourists", headers=admin_headers).json()
    for t in tourists:
        _mark_missing(client, admin_headers, t["id"])

    r = client.get("/api/efirs", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == len(tourists)


def test_efir_endpoints_require_admin(client, tourist_headers, db):
    t = make_tourist(db, name="Someone")
    for path in ["/api/efirs", "/api/efirs/1", "/api/efirs/1/pdf"]:
        assert client.get(path, headers=tourist_headers).status_code == 403
    assert client.post(f"/api/tourists/{t.id}/mark-missing",
                       headers=tourist_headers).status_code == 403


def test_document_hash_matches_canonical_content(client, admin_headers, db):
    """Regression pin for the hash the PDF and the chain both rely on."""
    t = make_tourist(db)
    eid = _mark_missing(client, admin_headers, t.id)["efir_id"]
    efir = db.get(EFIR, eid)
    tourist = db.get(type(t), t.id)
    assert efir.document_hash == compute_document_hash(efir, tourist)


def test_pdf_renders_even_with_no_last_location(db):
    """A tourist marked missing with no recorded ping yet must not crash PDF
    rendering -- last_known_lat/lng can legitimately be None."""
    t = make_tourist(db)
    t.last_lat = None
    t.last_lng = None
    db.commit()

    efir = EFIR(
        fir_number="EFIR/TEST/00001", incident_id=1, tourist_id=t.id, status="filed",
        narrative="Test narrative.", last_known_lat=None, last_known_lng=None,
        last_seen_at=None, document_hash="placeholder", filed_at=t.created_at,
    )
    pdf = render_efir_pdf(efir, t)
    assert pdf[:4] == b"%PDF"


@pytest.mark.parametrize("special", ["O'Brien-Test", "Test<Name>", 'Quote"Name'])
def test_pdf_handles_special_characters_in_name(db, special):
    """ReportLab's Paragraph treats content as mini-HTML; unescaped angle
    brackets or ampersands in a tourist's name must not break rendering."""
    t = make_tourist(db, name=special)
    efir = EFIR(
        fir_number="EFIR/TEST/00002", incident_id=1, tourist_id=t.id, status="filed",
        narrative=f"Report for {special} & co.", last_known_lat=26.1,
        last_known_lng=91.7, last_seen_at=None, document_hash="placeholder",
        filed_at=t.created_at,
    )
    pdf = render_efir_pdf(efir, t)
    assert pdf[:4] == b"%PDF"


def test_narrative_with_xml_special_chars_is_not_silently_truncated(db):
    """Regression test: ReportLab's Paragraph parses '<'/'&' as XML markup and,
    given an unrecognised tag, silently drops it and everything after it on
    that line rather than raising. A narrative containing a raw '<' used to
    lose the rest of the sentence in the rendered document -- a real legal-
    document integrity bug, not just a crash risk."""
    from pypdf import PdfReader

    t = make_tourist(db, name="Priya Singh")
    narrative = "Last seen near <Restricted Zone> boundary & did not return."
    efir = EFIR(
        fir_number="EFIR/TEST/00003", incident_id=1, tourist_id=t.id, status="filed",
        narrative=narrative, last_known_lat=26.1, last_known_lng=91.7,
        last_seen_at=None, document_hash="placeholder", filed_at=t.created_at,
    )
    pdf_bytes = render_efir_pdf(efir, t)

    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
    # The full sentence, including the part after '<', must survive verbatim.
    assert "did not return" in text
    assert "Restricted Zone" in text
