"""Render the analytics dashboard as a one-click PDF report.

The visual counterpart to the CSV export already on the Analytics page. Built
from the same aggregate queries the dashboard uses (see app/api/analytics.py)
via ReportLab -- the same library and escaping approach already used for
E-FIR documents (see services/efir_pdf.py), so no new dependency is needed.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.config import settings


def _table(headers: list[str], rows: list[list], col_widths: list[float]) -> Table:
    data = [headers] + rows
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    return t


def render_analytics_pdf(
    summary: dict, over_time: list[dict], by_type: list[dict],
    zone_risk: list[dict], severity: list[dict],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=16, spaceAfter=2)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=9,
                                    textColor=colors.HexColor("#64748b"))
    section_style = ParagraphStyle("Section", parent=styles["Heading3"],
                                   spaceBefore=14, spaceAfter=6)

    story = [
        Paragraph("Analytics &amp; Reporting", title_style),
        Paragraph(settings.PROJECT_NAME, subtitle_style),
        Paragraph(f"Generated {datetime.now().isoformat(sep=' ', timespec='seconds')}",
                  subtitle_style),
        Spacer(1, 10),
    ]

    story.append(Paragraph("Summary", section_style))
    summary_rows = [
        ["Total tourists", str(summary["total_tourists"]), "Active", str(summary["active_tourists"])],
        ["SOS active", str(summary["sos_active"]), "Missing", str(summary["missing"])],
        ["Total incidents", str(summary["total_incidents"]), "Open incidents", str(summary["open_incidents"])],
        ["Active alerts", str(summary["active_alerts"]), "Risk zones", str(summary["total_zones"])],
        ["Avg safety score", str(summary["avg_safety_score"]),
         "Avg response time (s)", str(summary["avg_response_time_seconds"])],
    ]
    story.append(_table(["Metric", "Value", "Metric", "Value"], summary_rows,
                        [45 * mm, 35 * mm, 45 * mm, 35 * mm]))

    if severity:
        story.append(Paragraph("Incident Severity Breakdown", section_style))
        story.append(_table(["Severity", "Count"],
                            [[s["severity"], str(s["count"])] for s in severity],
                            [80 * mm, 80 * mm]))

    if by_type:
        story.append(Paragraph("Alerts by Type", section_style))
        story.append(_table(["Type", "Count"],
                            [[a["type"], str(a["count"])] for a in by_type],
                            [80 * mm, 80 * mm]))

    if zone_risk:
        story.append(Paragraph("Zone-wise Crime Index", section_style))
        story.append(_table(
            ["Zone", "Risk level", "Crime index", "Alerts"],
            [[z["zone"], z["risk_level"], str(z["crime_index"]), str(z["alert_count"])]
             for z in zone_risk],
            [55 * mm, 35 * mm, 35 * mm, 35 * mm],
        ))

    if over_time:
        story.append(Paragraph("Incidents Over Time", section_style))
        story.append(_table(["Date", "Incidents"],
                            [[d["date"], str(d["count"])] for d in over_time],
                            [80 * mm, 80 * mm]))

    doc.build(story)
    return buf.getvalue()
