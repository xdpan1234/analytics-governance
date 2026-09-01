from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import DateRange, ReportError, ReportRequest


def _as_of(config: dict[str, Any] | None, explicit: date | None) -> date:
    if explicit:
        return explicit
    timezone = config.get("report_timezone", "Asia/Shanghai") if config else "Asia/Shanghai"
    return datetime.now(ZoneInfo(timezone)).date()


def completed_weeks(as_of: date) -> tuple[DateRange, DateRange]:
    current_end = as_of - timedelta(days=as_of.weekday() + 1)
    current = DateRange(current_end - timedelta(days=6), current_end)
    previous_end = current.start_date - timedelta(days=1)
    return current, DateRange(previous_end - timedelta(days=6), previous_end)


def resolve_request(config: dict[str, Any] | None, args: Any) -> ReportRequest:
    timezone_name = config.get("report_timezone", "Asia/Shanghai") if config else "Asia/Shanghai"
    try:
        ZoneInfo(timezone_name)
    except (TypeError, ZoneInfoNotFoundError) as error:
        raise ReportError("config report_timezone is invalid") from error
    as_of = _as_of(config, args.as_of)
    if bool(args.start_date) != bool(args.end_date):
        raise ReportError("--start-date and --end-date must be provided together")
    if args.start_date:
        report_range = DateRange(args.start_date, args.end_date)
        if report_range.end_date >= as_of:
            raise ReportError("report end date must be before as-of date")
    elif args.preset == "recent_7_complete_days":
        end = as_of - timedelta(days=1)
        report_range = DateRange(end - timedelta(days=6), end)
    else:
        report_range, _ = completed_weeks(as_of)
    if args.no_compare:
        comparison = None
    elif bool(args.compare_start_date) != bool(args.compare_end_date):
        raise ReportError("--compare-start-date and --compare-end-date must be provided together")
    elif args.compare_start_date:
        comparison = DateRange(args.compare_start_date, args.compare_end_date)
    else:
        end = report_range.start_date - timedelta(days=1)
        comparison = DateRange(end - timedelta(days=report_range.days - 1), end)
    if comparison and comparison.end_date >= as_of:
        raise ReportError("comparison end date must be before as-of date")
    return ReportRequest(report_range, comparison, timezone_name, config.get("environment") if config else None)
