#!/usr/bin/env python3
"""Generate a normalized GA4 abnormal-outcome report and render it for a channel."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from ga4_report.calculator import calculate_report
from ga4_report.contracts import ReportError, ReportRequest
from ga4_report.data import (
    FixtureDataSource,
    Ga4DataSource,
    load_config,
    load_fixture,
    parse_rows,
    response_headers,
)
from ga4_report.rendering import (
    FeishuDelivery,
    FeishuRenderer,
    HtmlRenderer,
    JsonRenderer,
    build_failure_card,
)
from ga4_report.request import completed_weeks as _completed_weeks
from ga4_report.request import resolve_request
from ga4_report.rules import OUTCOME_RULES, RULES_VERSION, validate_rules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Read fixed Data API responses from JSON.")
    parser.add_argument("--config", type=Path, help="Read local runtime configuration.")
    parser.add_argument("--preview", action="store_true", help="Print the rendered payload without delivery.")
    parser.add_argument("--output", "--format", dest="output", choices=("feishu", "json", "html"), default="feishu")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Date used to resolve date presets.")
    parser.add_argument(
        "--preset",
        choices=("previous_complete_day", "previous_complete_week", "recent_7_complete_days"),
        default="previous_complete_day",
    )
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--compare-start-date", type=date.fromisoformat)
    parser.add_argument("--compare-end-date", type=date.fromisoformat)
    parser.add_argument("--no-compare", action="store_true")
    return parser.parse_args()


def completed_weeks(as_of: date) -> tuple[tuple[date, date], tuple[date, date]]:
    current, previous = _completed_weeks(as_of)
    return (current.start_date, current.end_date), (previous.start_date, previous.end_date)


def validate_rules_against_schema() -> None:
    validate_rules(OUTCOME_RULES)


def build_card(report_data: dict[str, Any], as_of: date) -> dict[str, Any]:
    """Compatibility helper for callers that used the old raw fixture boundary."""
    current, previous = _completed_weeks(as_of)
    request = ReportRequest(current, previous, "Asia/Shanghai")
    facts = FixtureDataSource(report_data, OUTCOME_RULES).fetch(request)
    report = calculate_report(request, facts, OUTCOME_RULES, RULES_VERSION)
    return FeishuRenderer().render(report)


def _render(report: dict[str, Any], output: str, config: dict[str, Any] | None = None) -> dict[str, Any] | str:
    if output == "json":
        return JsonRenderer().render(report)
    if output == "html":
        return HtmlRenderer().render(report)
    return FeishuRenderer().render(report, config)


def _print_rendered(rendered: dict[str, Any] | str) -> None:
    print(rendered if isinstance(rendered, str) else json.dumps(rendered, ensure_ascii=False, separators=(",", ":")))


def main() -> int:
    args = parse_args()
    config: dict[str, Any] | None = None
    request: ReportRequest | None = None
    try:
        validate_rules_against_schema()
        config = load_config(args.config) if args.config else None
        if not args.fixture and not config:
            raise ReportError("--config is required for live GA4 mode")
        request = resolve_request(config, args)
        source = FixtureDataSource(load_fixture(args.fixture), OUTCOME_RULES) if args.fixture else Ga4DataSource(config, OUTCOME_RULES)
        facts = source.fetch(request)
        report = calculate_report(request, facts, OUTCOME_RULES, RULES_VERSION)
        rendered = _render(report, args.output, config)
    except (ReportError, KeyError, TypeError, ValueError, AttributeError) as error:
        if config and request and args.output == "feishu" and not args.preview:
            try:
                FeishuDelivery().send(build_failure_card(request), config)
            except ReportError:
                print("error: Feishu failure notification could not be delivered", file=sys.stderr)
        message = str(error) if isinstance(error, ReportError) else "report response is invalid"
        print(f"error: {message}", file=sys.stderr)
        return 1

    if args.preview or args.output != "feishu":
        _print_rendered(rendered)
        return 0
    if not config:
        print("error: --config is required for Feishu delivery", file=sys.stderr)
        return 1
    try:
        FeishuDelivery().send(rendered, config)
    except ReportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("sent GA4 abnormal-outcome report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
