from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import DateRange, ReportError, ReportRequest
from .rules import OutcomeRule, schema_contract


@dataclass(frozen=True)
class ReasonFact:
    reason: str
    platform: str
    app_version: str
    event_count: int
    context_count: int


@dataclass(frozen=True)
class PeriodFacts:
    outcomes: dict[str, dict[str, int]]
    affected_users: int
    active_users: int
    reasons: dict[str, list[ReasonFact]]
    hidden_unapproved_reason_count: int = 0


@dataclass(frozen=True)
class NormalizedFacts:
    current: PeriodFacts
    previous: PeriodFacts | None
    metadata_dimensions: frozenset[str]
    warnings: tuple[str, ...]
    hidden_unapproved_reason_count: int = 0


def response_headers(response: Any) -> tuple[list[str], list[str]]:
    if not isinstance(response, dict):
        raise ReportError("Data API response is invalid")
    dimension_headers = response.get("dimensionHeaders")
    metric_headers = response.get("metricHeaders")
    if dimension_headers is None and isinstance(metric_headers, list):
        raw_rows = response.get("rows", [])
        if isinstance(raw_rows, list) and all(
            isinstance(row, dict) and not row.get("dimensionValues") for row in raw_rows
        ):
            dimension_headers = []
    if not isinstance(dimension_headers, list) or not isinstance(metric_headers, list):
        raise ReportError("Data API response is missing headers")
    try:
        dimensions = [header["name"] for header in dimension_headers]
        metrics = [header["name"] for header in metric_headers]
    except (KeyError, TypeError) as error:
        raise ReportError("Data API response headers are invalid") from error
    if not all(isinstance(name, str) and name for name in dimensions + metrics):
        raise ReportError("Data API response headers are invalid")
    return dimensions, metrics


def parse_rows(response: Any, required_fields: set[str] | None = None) -> list[dict[str, str]]:
    dimensions, metrics = response_headers(response)
    if required_fields and not required_fields.issubset(set(dimensions + metrics)):
        raise ReportError("Data API response is missing required headers")
    raw_rows = response.get("rows", [])
    if not isinstance(raw_rows, list):
        raise ReportError("Data API response rows are invalid")
    rows: list[dict[str, str]] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ReportError("Data API response row is invalid")
        dimension_values = row.get("dimensionValues", [])
        metric_values = row.get("metricValues", [])
        if not isinstance(dimension_values, list) or not isinstance(metric_values, list):
            raise ReportError("Data API response values are invalid")
        if len(dimension_values) != len(dimensions) or len(metric_values) != len(metrics):
            raise ReportError("Data API response value count does not match headers")
        try:
            values = [item["value"] for item in dimension_values]
            values += [item["value"] for item in metric_values]
        except (KeyError, TypeError) as error:
            raise ReportError("Data API response value is invalid") from error
        if not all(isinstance(value, str) for value in values):
            raise ReportError("Data API response value is invalid")
        rows.append(dict(zip(dimensions + metrics, values, strict=True)))
    return rows


def _int(value: str, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ReportError(f"Data API {label} is invalid") from error


def _scalar_metric(response: dict[str, Any], metric: str) -> int:
    rows = parse_rows(response, {metric})
    return _int(rows[0][metric], metric) if rows else 0


def _outcome_values(response: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        row["eventName"]: {
            "eventCount": _int(row["eventCount"], "eventCount"),
            "totalUsers": _int(row["totalUsers"], "totalUsers"),
        }
        for row in parse_rows(response, {"eventName", "eventCount", "totalUsers"})
    }


def _reason_values(
    reports: dict[str, Any], rules: tuple[OutcomeRule, ...]
) -> tuple[dict[str, list[ReasonFact]], int]:
    if not isinstance(reports, dict):
        raise ReportError("Data API reason report is invalid")
    _, schema_allowed_values = schema_contract()
    rules_by_event = {rule.event_name: rule for rule in rules}
    grouped: dict[str, dict[str, dict[tuple[str, str], int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    hidden_unapproved = 0
    for reason_dimension, response in reports.items():
        for row in parse_rows(response, {"eventName", reason_dimension, "eventCount"}):
            event_name = row["eventName"]
            reason = row.get(reason_dimension, "")
            rule = rules_by_event.get(event_name)
            approved = schema_allowed_values.get(event_name, {}).get(
                reason_dimension.removeprefix("customEvent:"), frozenset()
            )
            if not rule or rule.reason_dimension != reason_dimension or reason in {"", "(not set)"} or reason not in approved:
                if reason not in {"", "(not set)"}:
                    hidden_unapproved += _int(row["eventCount"], "eventCount")
                continue
            platform = row.get("platform", "unknown")
            app_version = row.get("appVersion", "unknown")
            grouped[event_name][reason][(platform, app_version)] += _int(row["eventCount"], "eventCount")
    result: dict[str, list[ReasonFact]] = {}
    for event_name, event_reasons in grouped.items():
        values: list[ReasonFact] = []
        for reason, contexts in event_reasons.items():
            (platform, app_version), context_count = min(
                contexts.items(), key=lambda item: (-item[1], item[0])
            )
            values.append(
                ReasonFact(
                    reason=reason,
                    platform=platform,
                    app_version=app_version,
                    context_count=context_count,
                    event_count=sum(contexts.values()),
                )
            )
        result[event_name] = sorted(values, key=lambda item: (-item.event_count, item.reason))
    return result, hidden_unapproved


def access_token(config: dict[str, Any]) -> str:
    if token := os.environ.get("GA4_ACCESS_TOKEN"):
        return token
    gcloud = config.get("gcloud_bin") or shutil.which("gcloud")
    if not gcloud:
        raise ReportError("gcloud is required to refresh personal ADC")
    try:
        result = subprocess.run(
            [gcloud, "auth", "application-default", "print-access-token"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReportError("personal ADC access token could not be refreshed") from error
    token = result.stdout.strip()
    if result.returncode or not token:
        raise ReportError("personal ADC is unavailable; run gcloud auth application-default login")
    return token


def request_json(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    encoded = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=encoded,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ReportError("Data API response is too large")
            payload = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ReportError(f"Data API request failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ReportError("Data API request could not be completed") from error
    except json.JSONDecodeError as error:
        raise ReportError("Data API response is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ReportError("Data API response is invalid")
    return payload


def _base_url(config: dict[str, Any]) -> str:
    url = str(os.environ.get("GA4_DATA_API_BASE_URL") or config.get("data_api_base_url", "")).rstrip("/")
    if not url:
        raise ReportError("Data API base URL is missing")
    if url.startswith("https://") or url.startswith(("http://127.0.0.1:", "http://localhost:")):
        return url
    raise ReportError("Data API base URL must use HTTPS")


def _environment_filter(environment: str) -> dict[str, Any]:
    return {"filter": {"fieldName": "customEvent:environment", "stringFilter": {"matchType": "EXACT", "value": environment, "caseSensitive": True}}}


def _filter(event_names: list[str], environment: str | None) -> dict[str, Any]:
    event = {"filter": {"fieldName": "eventName", "inListFilter": {"values": event_names, "caseSensitive": True}}}
    if not environment:
        return event
    return {"andGroup": {"expressions": [event, _environment_filter(environment)]}}


def _run_report(base_url: str, property_id: str, token: str, period: DateRange, dimensions: list[str], metrics: list[str], dimension_filter: dict[str, Any] | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "dateRanges": [{"startDate": period.start_date.isoformat(), "endDate": period.end_date.isoformat()}],
        "dimensions": [{"name": name} for name in dimensions],
        "metrics": [{"name": name} for name in metrics],
        "limit": "100000",
    }
    if dimension_filter:
        body["dimensionFilter"] = dimension_filter
    return request_json("POST", f"{base_url}/properties/{property_id}:runReport", token, body)


def _period_from_api(base_url: str, config: dict[str, Any], token: str, period: DateRange, metadata_dimensions: frozenset[str], rules: tuple[OutcomeRule, ...]) -> PeriodFacts:
    property_id = str(config["property_id"])
    abnormal_names = [rule.event_name for rule in rules]
    outcome_names = sorted(set(abnormal_names) | {rule.denominator_event for rule in rules if rule.denominator_event})
    environment = config.get("environment") if "customEvent:environment" in metadata_dimensions else None
    outcomes = _run_report(base_url, property_id, token, period, ["eventName"], ["eventCount", "totalUsers"], _filter(outcome_names, environment))
    affected = _run_report(base_url, property_id, token, period, [], ["totalUsers"], _filter(abnormal_names, environment))
    active = _run_report(base_url, property_id, token, period, [], ["activeUsers"], _environment_filter(environment) if environment else None)
    reason_reports: dict[str, Any] = {}
    for dimension in sorted({rule.reason_dimension for rule in rules} & set(metadata_dimensions)):
        event_names = [rule.event_name for rule in rules if rule.reason_dimension == dimension]
        dimensions = ["eventName", dimension]
        dimensions.extend(name for name in ("platform", "appVersion") if name in metadata_dimensions)
        reason_reports[dimension] = _run_report(base_url, property_id, token, period, dimensions, ["eventCount"], _filter(event_names, environment))
    reasons, hidden = _reason_values(reason_reports, rules)
    return PeriodFacts(_outcome_values(outcomes), _scalar_metric(affected, "totalUsers"), _scalar_metric(active, "activeUsers"), reasons, hidden)


class Ga4DataSource:
    def __init__(self, config: dict[str, Any], rules: tuple[OutcomeRule, ...]):
        self.config = config
        self.rules = rules

    def fetch(self, request: ReportRequest) -> NormalizedFacts:
        token = access_token(self.config)
        base_url = _base_url(self.config)
        property_id = str(self.config["property_id"])
        metadata = request_json("GET", f"{base_url}/properties/{property_id}/metadata", token)
        raw_dimensions = metadata.get("dimensions", [])
        if not isinstance(raw_dimensions, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("apiName"), str) or not item["apiName"]
            for item in raw_dimensions
        ):
            raise ReportError("Data API metadata is invalid")
        metadata_dimensions = frozenset(
            item.get("apiName", "") for item in raw_dimensions if isinstance(item, dict)
        )
        warnings: list[str] = []
        if not request.environment:
            warnings.append("未配置 environment，数据未按环境过滤")
        elif "customEvent:environment" not in metadata_dimensions:
            warnings.append("环境维度未注册，未应用 environment 过滤")
        missing_context = [name for name in ("platform", "appVersion") if name not in metadata_dimensions]
        if missing_context:
            warnings.append("原因上下文维度不可用：" + "、".join(missing_context))
        current = _period_from_api(base_url, self.config, token, request.report_range, metadata_dimensions, self.rules)
        previous = _period_from_api(base_url, self.config, token, request.comparison_range, metadata_dimensions, self.rules) if request.comparison_range else None
        return NormalizedFacts(
            current,
            previous,
            metadata_dimensions,
            tuple(warnings),
            current.hidden_unapproved_reason_count,
        )


class FixtureDataSource:
    def __init__(self, fixture: dict[str, Any], rules: tuple[OutcomeRule, ...]):
        self.fixture = fixture
        self.rules = rules

    def fetch(self, request: ReportRequest) -> NormalizedFacts:
        metadata = self.fixture.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ReportError("fixture metadata is invalid")
        dimensions = metadata.get("dimensions", [])
        if not isinstance(dimensions, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("apiName"), str) or not item["apiName"]
            for item in dimensions
        ):
            raise ReportError("fixture metadata is invalid")
        metadata_dimensions = frozenset(item.get("apiName", "") for item in dimensions if isinstance(item, dict))
        reports = self.fixture.get("reports")
        if not isinstance(reports, dict) or not isinstance(reports.get("current"), dict):
            raise ReportError("fixture must contain metadata and reports")
        def period(name: str) -> PeriodFacts:
            raw = reports.get(name)
            if not isinstance(raw, dict):
                raise ReportError("fixture report period is invalid")
            outcomes = raw.get("outcomes")
            affected = raw.get("affected_users")
            active = raw.get("active_users")
            if not isinstance(outcomes, dict) or not isinstance(affected, dict) or not isinstance(active, dict):
                raise ReportError("fixture report period is invalid")
            reasons, hidden = _reason_values(raw.get("reasons", {}), self.rules)
            return PeriodFacts(_outcome_values(outcomes), _scalar_metric(affected, "totalUsers"), _scalar_metric(active, "activeUsers"), reasons, hidden)
        warnings: tuple[str, ...] = ()
        current = period("current")
        previous = period("previous") if request.comparison_range else None
        return NormalizedFacts(
            current,
            previous,
            metadata_dimensions,
            warnings,
            current.hidden_unapproved_reason_count,
        )


def load_fixture(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportError("fixture could not be read") from error
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict) or not isinstance(data.get("reports"), dict):
        raise ReportError("fixture must contain metadata and reports")
    return data


def load_config(path: Path | None) -> dict[str, Any]:
    if not path:
        raise ReportError("--config is required for live GA4 mode")
    try:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ReportError("config permissions must be 0600")
        config = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ReportError("config could not be read") from error
    except json.JSONDecodeError as error:
        raise ReportError("config is not valid JSON") from error
    if not isinstance(config, dict):
        raise ReportError("config is not an object")
    if not str(config.get("property_id", "")).isdigit():
        raise ReportError("config property_id must contain digits only")
    if config.get("environment") not in (None, "prod"):
        raise ReportError("config environment must be prod when set")
    return config
