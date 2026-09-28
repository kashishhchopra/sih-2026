"""Render a filed EFIR record as a PDF document.

The document is rebuilt from the persisted EFIR row on every request rather
than stored as a binary blob -- the row is the source of truth, the PDF is a
deterministic presentation of it, and re-rendering means a ReportLab version
bump can't silently desynchronise a stored file from what the API would
generate today.
"""
import hashlib
import io
import json
from xml.sax.saxutils import escape

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.efir import EFIR
from app.models.tourist import Tourist


def canonical_document(efir: EFIR, tourist: Tourist) -> str:
    """The exact text whose hash is chained. Stable field order and formatting
    so the hash is reproducible from the stored row alone."""
    payload = {
        "fir_number": efir.fir_number,
        "status": efir.status,
        "subject_name": tourist.full_name,
        "subject_digital_id": tourist.digital_id,
        "subject_document": tourist.document_number,
        "narrative": efir.narrative,
        "last_known_lat": efir.last_known_lat,
        "last_known_lng": efir.last_known_lng,
        "last_seen_at": efir.last_seen_at.isoformat() if efir.last_seen_at else None,
        "filed_at": efir.filed_at.isoformat(),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def compute_document_hash(efir: EFIR, tourist: Tourist) -> str:
    return hashlib.sha256(canonical_document(efir, tourist).encode()).hexdigest()


def _qr_image(fir_number: str, doc_hash: str) -> Image:
    payload = json.dumps({"fir_number": fir_number, "verify_hash": doc_hash[:16]})
    qr = qrcode.make(payload)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=28 * mm, height=28 * mm)


def render_efir_pdf(efir: EFIR, tourist: Tourist) -> bytes:
    """Build the PDF and return its raw bytes.

    ReportLab's Paragraph parses its input as a small XML dialect (it supports
    tags like <b> and <br/>), so any '<', '>' or '&' in tourist-controlled text
    -- a name, a narrative -- must be escaped before being wrapped in a
    Paragraph. Unescaped, ReportLab does not raise: it silently drops the
    unrecognised "tag" and everything inside it, which would corrupt a legal
    document instead of failing loudly. Every Paragraph() call below that
    wraps free text goes through escape() -- Table cells are plain text and
    must NOT be escaped, or the entities would render literally.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("EfirTitle", parent=styles["Title"], fontSize=16,
                                 spaceAfter=2)
    subtitle_style = ParagraphStyle("EfirSubtitle", parent=styles["Normal"],
                                    textColor=colors.HexColor("#64748b"), fontSize=9)
    section_style = ParagraphStyle("EfirSection", parent=styles["Heading3"],
                                   spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle("EfirBody", parent=styles["Normal"], leading=14)
    mono_style = ParagraphStyle("EfirMono", parent=styles["Normal"], fontName="Courier",
                                fontSize=8, textColor=colors.HexColor("#475569"))

    header_row = Table(
        [[
            [
                Paragraph("ELECTRONIC FIRST INFORMATION REPORT", title_style),
                Paragraph("MUSAFIR — Smart Tourist Safety Monitoring &amp; Incident Response System",
                         subtitle_style),
            ],
            _qr_image(efir.fir_number, efir.document_hash),
        ]],
        colWidths=[130 * mm, 30 * mm],
    )
    header_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))

    meta = Table([
        ["FIR Number", efir.fir_number, "Status", efir.status.upper()],
        ["Filed At", efir.filed_at.isoformat(sep=" ", timespec="seconds"), "Incident ID",
         str(efir.incident_id)],
    ], colWidths=[28 * mm, 60 * mm, 25 * mm, 47 * mm])
    meta.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))

    # Table cells render plain text as-is -- unlike Paragraph, they are NOT run
    # through the XML mini-parser, so escaping here would display literal
    # "&amp;" instead of "&". Only Paragraph() calls below need escape().
    subject = Table([
        ["Name", tourist.full_name, "Nationality", tourist.nationality],
        ["Digital Tourist ID", tourist.digital_id, "Document",
         f"{tourist.document_type.upper()} {tourist.document_number}"],
        ["Phone", tourist.phone, "", ""],
    ], colWidths=[35 * mm, 60 * mm, 30 * mm, 35 * mm])
    subject.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    location_line = "Unknown"
    if efir.last_known_lat is not None:
        location_line = f"{efir.last_known_lat:.5f}, {efir.last_known_lng:.5f}"
        if efir.last_seen_at:
            location_line += f" at {efir.last_seen_at.isoformat(sep=' ', timespec='minutes')}"

    story = [
        header_row,
        Spacer(1, 10),
        meta,
        Paragraph("Subject", section_style),
        subject,
        Paragraph("Last Known Location", section_style),
        Paragraph(escape(location_line), body_style),
        Paragraph("Narrative", section_style),
        Paragraph(escape(efir.narrative), body_style),
        Spacer(1, 14),
        Paragraph(
            "Document integrity", section_style,
        ),
        Paragraph(
            "This report's content hash is appended to the subject's tamper-evident "
            "digital-ID chain as an EFIR_FILED block. Any alteration to this document "
            "after filing is independently detectable by re-verifying that chain.",
            body_style,
        ),
        Paragraph(f"SHA-256: {escape(efir.document_hash)}", mono_style),
    ]
    doc.build(story)
    return buf.getvalue()
