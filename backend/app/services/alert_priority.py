"""AI Alert Prioritization: a ranking layer over the alerts you already generate.

No new model or dataset is needed here -- every input already flows through the
monitoring pipeline (severity, alert type, the zone an alert fired in, if any).
Each alert gets a priority score and is bucketed into critical/high/medium/low
so an operator working a flood of alerts can triage by real urgency instead of
arrival order.
"""
from __future__ import annotations

from app.models.alert import Alert
from app.models.zone import Zone

# Weights are additive and deliberately simple/explainable -- this mirrors the
# rest of the project's "transparent scoring" style (see services/explain.py)
# rather than hiding the ranking behind an opaque model.
_SEVERITY_WEIGHT = {"critical": 40, "high": 28, "medium": 14, "low": 4}
_TYPE_WEIGHT = {
    "sos": 40, "anomaly": 20, "inactivity": 18, "geofence": 16, "route_deviation": 12,
}
# How isolated/dangerous the zone an alert fired in is -- an alert in a
# "restricted" zone is more urgent than the identical alert in a "low" zone.
_ISOLATION_WEIGHT = {"restricted": 20, "high": 14, "medium": 6, "low": 0}

_CRITICAL_MIN = 55
_HIGH_MIN = 38
_MEDIUM_MIN = 20


def score_alert(alert: Alert, zone: Zone | None) -> float:
    score = _SEVERITY_WEIGHT.get(alert.severity, 10)
    score += _TYPE_WEIGHT.get(alert.type, 8)
    if zone is not None:
        score += _ISOLATION_WEIGHT.get(zone.risk_level, 0)
    return round(score, 1)


def bucket(score: float) -> str:
    if score >= _CRITICAL_MIN:
        return "critical"
    if score >= _HIGH_MIN:
        return "high"
    if score >= _MEDIUM_MIN:
        return "medium"
    return "low"


def prioritize(alerts: list[Alert], zones_by_id: dict[int, Zone]) -> list[dict]:
    """Score + bucket every alert, ranked highest priority first."""
    ranked = []
    for a in alerts:
        zone = zones_by_id.get(a.zone_id) if a.zone_id else None
        score = score_alert(a, zone)
        ranked.append({"alert": a, "priority_score": score, "priority": bucket(score)})
    ranked.sort(key=lambda r: r["priority_score"], reverse=True)
    return ranked
