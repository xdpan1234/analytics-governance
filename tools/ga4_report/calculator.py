from __future__ import annotations

from typing import Any

from .contracts import ReportRequest, metric
from .data import NormalizedFacts, PeriodFacts
from .rules import OutcomeRule


def _change(current: int | float, previous: int | float | None) -> tuple[str, float | None]:
    if previous is None:
        return "not_compared", None
    if previous == 0:
        return ("new", None) if current else ("available", 0.0)
    return "available", (current - previous) / previous


def _count(value: int, previous: int | None) -> dict[str, Any]:
    status, delta = _change(value, previous)
    return metric(value, status=status, previous=previous, delta=delta)


def _rate(rule: OutcomeRule, event_count: int, outcomes: dict[str, dict[str, int]], previous: PeriodFacts | None) -> dict[str, Any] | None:
    if not rule.denominator_event:
        return None
    denominator_count = outcomes.get(rule.denominator_event, {}).get("eventCount", 0)
    denominator = denominator_count if rule.outcome_type == "blocked" else denominator_count + event_count
    if denominator == 0:
        return metric(None, status="unavailable_zero_denominator", numerator=event_count, denominator=0)
    value = event_count / denominator
    previous_value: float | None = None
    if previous:
        previous_event_count = previous.outcomes.get(rule.event_name, {}).get("eventCount", 0)
        previous_denominator_count = previous.outcomes.get(rule.denominator_event, {}).get("eventCount", 0)
        previous_denominator = previous_denominator_count if rule.outcome_type == "blocked" else previous_denominator_count + previous_event_count
        if previous_denominator:
            previous_value = previous_event_count / previous_denominator
    delta = value - previous_value if previous_value is not None else None
    return metric(value, numerator=event_count, denominator=denominator, previous=previous_value, delta=delta)


def _per_thousand(value: int, active_users: int, previous_count: int | None, previous_active_users: int | None) -> dict[str, Any]:
    if not active_users:
        return metric(None, status="unavailable_zero_denominator", numerator=value, denominator=0)
    previous_value = None
    if previous_count is not None and previous_active_users:
        previous_value = previous_count / previous_active_users * 1000
    calculated = value / active_users * 1000
    return metric(calculated, numerator=value, denominator=active_users, previous=previous_value, delta=calculated - previous_value if previous_value is not None else None)


def calculate_report(request: ReportRequest, facts: NormalizedFacts, rules: tuple[OutcomeRule, ...], rules_version: str) -> dict[str, Any]:
    current = facts.current
    previous = facts.previous
    events: list[dict[str, Any]] = []
    for rule in rules:
        current_values = current.outcomes.get(rule.event_name, {"eventCount": 0, "totalUsers": 0})
        count = current_values["eventCount"]
        if count == 0:
            continue
        previous_count = previous.outcomes.get(rule.event_name, {}).get("eventCount", 0) if previous else None
        reasons = current.reasons.get(rule.event_name, [])
        reason_status = "available" if rule.reason_dimension in facts.metadata_dimensions else "unavailable_missing_dimension"
        coverage = sum(item.event_count for item in reasons) / count if count else None
        events.append(
            {
                "event_name": rule.event_name,
                "outcome_type": rule.outcome_type,
                "event_count": _count(count, previous_count),
                "affected_users": _count(current_values["totalUsers"], previous.outcomes.get(rule.event_name, {}).get("totalUsers") if previous else None),
                "rate": _rate(rule, count, current.outcomes, previous),
                "per_1000_active_users": _per_thousand(
                    count,
                    current.active_users,
                    previous.outcomes.get(rule.event_name, {}).get("eventCount") if previous else None,
                    previous.active_users if previous else None,
                ) if not rule.denominator_event else None,
                "reasons": {
                    "dimension": rule.reason_dimension,
                    "status": reason_status,
                    "coverage": metric(coverage, status=reason_status, numerator=sum(item.event_count for item in reasons), denominator=count) if coverage is not None else metric(None, status=reason_status, numerator=0, denominator=count),
                    "items": [
                        {
                            "reason": item.reason,
                            "platform": item.platform,
                            "app_version": item.app_version,
                            "event_count": item.event_count,
                            "context_count": item.context_count,
                        }
                        for item in reasons
                    ],
                },
            }
        )
    events.sort(key=lambda item: (-item["event_count"]["value"], item["event_name"]))
    previous_total = sum(previous.outcomes.get(rule.event_name, {}).get("eventCount", 0) for rule in rules) if previous else None
    total = sum(item["event_count"]["value"] for item in events)
    affected_previous = previous.affected_users if previous else None
    active_previous = previous.active_users if previous else None
    warnings = list(facts.warnings)
    if facts.hidden_unapproved_reason_count:
        warnings.append(f"已隐藏未批准原因值：{facts.hidden_unapproved_reason_count} 次")
    return {
        "report_schema_version": "1.0",
        "rules_version": rules_version,
        "period": request.report_range.as_dict(),
        "comparison_period": request.comparison_range.as_dict() if request.comparison_range else None,
        "summary": {
            "abnormal_event_count": _count(total, previous_total),
            "affected_users": _count(current.affected_users, affected_previous),
            "active_users": _count(current.active_users, active_previous),
        },
        "events": events,
        "quality": {
            "warnings": warnings,
            "missing_dimensions": sorted({rule.reason_dimension for rule in rules if rule.reason_dimension not in facts.metadata_dimensions}),
        },
    }
