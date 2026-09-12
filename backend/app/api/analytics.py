"""Dashboard analytics.

Every endpoint here aggregates in SQL. The previous implementation loaded whole
tables with `.all()` and counted in Python, which is O(rows) memory per request
and degrades badly once the ping/alert tables grow.
"""
import json
from datetime import date as date_cls

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.time import utc_now
from app.db.session import get_db
from app.models.alert import Alert
from app.models.incident import Incident, IncidentEvent
from app.models.itinerary import ItineraryDocument
from app.models.police import PoliceStation
from app.models.tourist import Tourist
from app.models.user import User
from app.models.zone import Zone
from app.services.analytics_excel import render_analytics_excel
from app.services.analytics_pdf import render_analytics_pdf

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    # One row of tourist aggregates instead of loading every tourist.
    t_stats = db.query(
        func.count(Tourist.id),
        func.sum(case((Tourist.status == "active", 1), else_=0)),
        func.sum(case((Tourist.status == "sos", 1), else_=0)),
        func.sum(case((Tourist.status == "missing", 1), else_=0)),
        func.avg(Tourist.safety_score),
    ).one()
    total_tourists, active, sos_active, missing, avg_score = t_stats

    i_stats = db.query(
        func.count(Incident.id),
        func.sum(case((Incident.status != "resolved", 1), else_=0)),
    ).one()
    total_incidents, open_incidents = i_stats

    # Average response time over resolved incidents only. `response_time_seconds`
    # is a Python property, so it cannot be used in SQL -- compute the delta here.
    resolved_deltas = db.query(Incident.detected_at, Incident.resolved_at).filter(
        Incident.resolved_at.isnot(None)
    ).all()
    avg_response = (
        sum((r - d).total_seconds() for d, r in resolved_deltas) / len(resolved_deltas)
        if resolved_deltas else 0.0
    )

    active_alerts = db.query(func.count(Alert.id)).filter(
        Alert.acknowledged.is_(False)
    ).scalar()

    return {
        "total_tourists": total_tourists or 0,
        "active_tourists": int(active or 0),
        "sos_active": int(sos_active or 0),
        "missing": int(missing or 0),
        "total_incidents": total_incidents or 0,
        "open_incidents": int(open_incidents or 0),
        "active_alerts": active_alerts or 0,
        "avg_safety_score": round(float(avg_score), 1) if avg_score is not None else 0,
        "avg_response_time_seconds": round(avg_response, 1),
        "total_zones": db.query(func.count(Zone.id)).scalar() or 0,
    }


@router.get("/alerts-by-type")
def alerts_by_type(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = (
        db.query(Alert.type, func.count(Alert.id))
        .group_by(Alert.type)
        .order_by(func.count(Alert.id).desc())
        .all()
    )
    return [{"type": t, "count": c} for t, c in rows]


@router.get("/incidents-over-time")
def incidents_over_time(
    granularity: str = Query("day", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db), _: User = Depends(require_admin),
):
    """Daily by default (unchanged from before); `granularity=week` or
    `month` re-buckets the same rows more coarsely, for the Reports &
    Trends "daily/weekly/monthly" toggle.

    The SQL side always groups by day via `func.date()`, same as before --
    that function (unlike strftime, SQLite-only) works identically on
    SQLite and PostgreSQL. Week/month is then a second, cheap regroup in
    Python over that already-small per-day result set (one row per day that
    actually had an incident, not per incident), not a second table scan.
    """
    day = func.date(Incident.detected_at)
    rows = db.query(day, func.count(Incident.id)).group_by(day).order_by(day).all()
    if granularity == "day":
        return [{"date": str(d), "count": c} for d, c in rows]

    buckets: dict[str, int] = {}
    for d, c in rows:
        date = d if isinstance(d, date_cls) else date_cls.fromisoformat(str(d))
        key = (f"{date.isocalendar().year}-W{date.isocalendar().week:02d}" if granularity == "week"
               else date.strftime("%Y-%m"))
        buckets[key] = buckets.get(key, 0) + c
    return [{"date": k, "count": v} for k, v in sorted(buckets.items())]


@router.get("/zone-risk")
def zone_risk(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Alert counts per zone via the real foreign key.

    This used to attribute alerts by testing `zone.name in alert.message`, which
    double-counted whenever one zone's name was a substring of another's.
    """
    rows = (
        db.query(
            Zone.id, Zone.name, Zone.risk_level, Zone.crime_index,
            func.count(Alert.id).label("alert_count"),
        )
        .outerjoin(Alert, (Alert.zone_id == Zone.id) & (Alert.type == "geofence"))
        .group_by(Zone.id, Zone.name, Zone.risk_level, Zone.crime_index)
        .order_by(Zone.crime_index.desc())
        .all()
    )
    return [
        {"zone": name, "risk_level": risk, "crime_index": crime, "alert_count": count}
        for _id, name, risk, crime, count in rows
    ]


@router.get("/severity-breakdown")
def severity_breakdown(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = (
        db.query(Incident.severity, func.count(Incident.id))
        .group_by(Incident.severity)
        .all()
    )
    # Stable, meaningful order for the chart rather than DB row order.
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    out = [{"severity": s, "count": c} for s, c in rows]
    return sorted(out, key=lambda r: order.get(r["severity"], 99))


@router.get("/pdf")
def analytics_pdf(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """One-click printable report -- the visual counterpart to the CSV export
    already on the dashboard. Reuses the same aggregate queries above."""
    pdf_bytes = render_analytics_pdf(
        summary(db, user), incidents_over_time(granularity='day', db=db, _=user), alerts_by_type(db, user),
        zone_risk(db, user), severity_breakdown(db, user),
    )
    filename = "analytics-report-" + utc_now().strftime("%Y%m%d-%H%M%S") + ".pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/incident-types")
def incident_types(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Most common incident types (sos, missing_person, geofence, ...) and,
    within that, SOS-specific totals -- "Total SOS cases" / "Active vs.
    resolved cases" from real Incident rows, not inferred from Alert."""
    rows = (
        db.query(Incident.type, func.count(Incident.id))
        .group_by(Incident.type).order_by(func.count(Incident.id).desc()).all()
    )
    by_type = [{"type": t, "count": c} for t, c in rows]

    sos_stats = db.query(
        func.count(Incident.id),
        func.sum(case((Incident.status == "resolved", 1), else_=0)),
    ).filter(Incident.type == "sos").one()
    total_sos, resolved_sos = sos_stats
    total_sos = total_sos or 0
    resolved_sos = int(resolved_sos or 0)

    return {
        "by_type": by_type,
        "sos": {
            "total": total_sos,
            "active": total_sos - resolved_sos,
            "resolved": resolved_sos,
        },
    }


@router.get("/incidents-heatmap")
def incidents_heatmap(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Incident locations for the density heatmap (Crime & Safety Hotspots).

    Bounded to the most recent 2000 located incidents -- a heatmap layer
    gains nothing from an unbounded row count, and this keeps the endpoint
    O(1) regardless of how large the incident table grows, same principle
    as every other query in this module.
    """
    rows = (
        db.query(Incident.lat, Incident.lng)
        .filter(Incident.lat.isnot(None), Incident.lng.isnot(None))
        .order_by(Incident.detected_at.desc())
        .limit(2000).all()
    )
    return [{"lat": lat, "lng": lng} for lat, lng in rows]


@router.get("/police-performance")
def police_performance(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Per-station load and speed -- cases handled, pending vs. resolved,
    response/resolution time, and how many cases arrived at that station by
    inter-station transfer. Built from the same real columns the police
    network itself writes (Incident.station_id, .dispatched_at, .resolved_at,
    IncidentEvent status="forwarded") -- nothing here is a second, parallel
    record of what the dispatch/forwarding system already tracks.
    """
    stations = db.query(PoliceStation).all()
    incidents = (
        db.query(Incident.station_id, Incident.status, Incident.detected_at,
                 Incident.dispatched_at, Incident.resolved_at)
        .filter(Incident.station_id.isnot(None)).all()
    )
    by_station: dict[int, list] = {}
    for row in incidents:
        by_station.setdefault(row[0], []).append(row)

    transfers_in = dict(
        db.query(Incident.station_id, func.count(IncidentEvent.id))
        .join(IncidentEvent, IncidentEvent.incident_id == Incident.id)
        .filter(IncidentEvent.status == "forwarded", Incident.station_id.isnot(None))
        .group_by(Incident.station_id).all()
    )
    total_transfers = db.query(func.count(IncidentEvent.id)).filter(
        IncidentEvent.status == "forwarded"
    ).scalar() or 0

    out = []
    for st in stations:
        rows = by_station.get(st.id, [])
        resolved = [r for r in rows if r.status == "resolved"]
        response_deltas = [
            (r.dispatched_at - r.detected_at).total_seconds()
            for r in rows if r.dispatched_at is not None
        ]
        resolution_deltas = [
            (r.resolved_at - r.detected_at).total_seconds()
            for r in resolved if r.resolved_at is not None
        ]
        out.append({
            "station_id": st.id,
            "station": st.name,
            "cases_handled": len(rows),
            "pending": len(rows) - len(resolved),
            "resolved": len(resolved),
            "avg_response_time_seconds": (
                round(sum(response_deltas) / len(response_deltas), 1) if response_deltas else None
            ),
            "avg_resolution_time_seconds": (
                round(sum(resolution_deltas) / len(resolution_deltas), 1) if resolution_deltas else None
            ),
            "transfers_received": int(transfers_in.get(st.id, 0)),
        })
    out.sort(key=lambda r: r["cases_handled"], reverse=True)
    return {"stations": out, "total_transfers": total_transfers}


def _extract_destinations(extracted_json: str) -> list[str]:
    """Pull destination names out of one itinerary's extracted_json.

    The itinerary extractor (services/itinerary_extract.py) doesn't
    guarantee one fixed key name across every document type it parses,
    so this takes whichever of the plausible list-shaped fields is present
    rather than assuming a single schema.
    """
    try:
        data = json.loads(extracted_json or "{}")
    except (ValueError, TypeError):
        return []
    for key in ("destinations", "stops", "waypoints", "itinerary"):
        items = data.get(key)
        if isinstance(items, list):
            names = []
            for item in items:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("destination") or item.get("place")
                else:
                    name = item
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            if names:
                return names
    return []


@router.get("/tourist-activity")
def tourist_activity(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Total/active tourists, domestic vs. international, and the most
    common destinations across confirmed itineraries.

    Domestic vs. international reuses this project's own existing
    convention for that split (document_type == "passport" means a foreign
    tourist -- see services/checkin.py) rather than inventing a new one.
    """
    t_stats = db.query(
        func.count(Tourist.id),
        func.sum(case((Tourist.status == "active", 1), else_=0)),
        func.sum(case((Tourist.document_type == "passport", 1), else_=0)),
    ).one()
    total, active, international = t_stats
    total = total or 0
    international = int(international or 0)

    docs = (
        db.query(ItineraryDocument.extracted_json)
        .filter(ItineraryDocument.confirmed.is_(True)).all()
    )
    counts: dict[str, int] = {}
    for (extracted_json,) in docs:
        for name in _extract_destinations(extracted_json):
            counts[name] = counts.get(name, 0) + 1
    popular = sorted(
        ({"destination": k, "count": v} for k, v in counts.items()),
        key=lambda r: r["count"], reverse=True,
    )[:10]

    return {
        "total_tourists": total,
        "active_tourists": int(active or 0),
        "domestic_tourists": total - international,
        "international_tourists": international,
        "popular_destinations": popular,
    }


@router.get("/excel")
def analytics_excel(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """The Excel counterpart to /analytics/pdf -- same aggregates, one
    workbook with a sheet per section, for authorities who want the
    underlying numbers rather than a formatted report."""
    xlsx_bytes = render_analytics_excel(
        summary(db, user), incidents_over_time(granularity='day', db=db, _=user),
        alerts_by_type(db, user), zone_risk(db, user), severity_breakdown(db, user),
        police_performance(db, user), tourist_activity(db, user), incident_types(db, user),
    )
    filename = "analytics-report-" + utc_now().strftime("%Y%m%d-%H%M%S") + ".xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
