#!/usr/bin/env python3
"""Generate a weekly GA4 abnormal-outcome report and optionally send it to Feishu."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class OutcomeRule:
    event_name: str
    outcome_type: str
    denominator_event: str | None
    reason_dimension: str


FAILURE_REASON = "customEvent:failure_reason"
OUTCOME_RULES = tuple(
    OutcomeRule(*values)
    for values in (
        ("account_login_failed", "failed", "account_login_completed", FAILURE_REASON),
        (
            "account_data_control_failed",
            "failed",
            "account_data_control_completed",
            FAILURE_REASON,
        ),
        (
            "account_username_rule_blocked",
            "blocked",
            "account_username_rule_evaluated",
            FAILURE_REASON,
        ),
        ("account_auth_state_invalidated", "invalidated", None, FAILURE_REASON),
        ("app_boot_degraded", "degraded", "app_boot_completed", FAILURE_REASON),
        (
            "app_legal_link_open_failed",
            "failed",
            "app_legal_link_opened",
            FAILURE_REASON,
        ),
        ("app_language_fallback_blocked", "blocked", None, FAILURE_REASON),
        ("contact_us_failed", "failed", "contact_us_opened", FAILURE_REASON),
        ("chat_response_failed", "failed", "chat_response_completed", FAILURE_REASON),
        ("chat_voice_start_failed", "failed", "chat_voice_started", FAILURE_REASON),
        ("device_entry_blocked", "blocked", None, FAILURE_REASON),
        (
            "device_binding_failed",
            "failed",
            "device_binding_completed",
            FAILURE_REASON,
        ),
        (
            "device_setting_update_failed",
            "failed",
            "device_setting_updated",
            FAILURE_REASON,
        ),
        ("device_sync_failed", "failed", "device_sync_completed", FAILURE_REASON),
        (
            "device_reconnect_failed",
            "failed",
            "device_reconnect_completed",
            FAILURE_REASON,
        ),
        (
            "device_version_gate_blocked",
            "blocked",
            "device_version_gate_evaluated",
            FAILURE_REASON,
        ),
        ("device_ota_failed", "failed", "device_ota_completed", FAILURE_REASON),
        (
            "device_usage_photo_capture_failed",
            "failed",
            "device_usage_photo_capture_succeeded",
            FAILURE_REASON,
        ),
        (
            "device_usage_video_record_failed",
            "failed",
            "device_usage_video_record_ended",
            FAILURE_REASON,
        ),
        (
            "device_usage_audio_record_failed",
            "failed",
            "device_usage_audio_record_ended",
            FAILURE_REASON,
        ),
        (
            "device_usage_ai_chat_failed",
            "failed",
            "device_usage_ai_chat_ended",
            FAILURE_REASON,
        ),
        (
            "device_usage_media_sync_failed",
            "failed",
            None,
            "customEvent:error_source",
        ),
        (
            "media_import_degraded",
            "degraded",
            "media_import_completed",
            FAILURE_REASON,
        ),
        ("media_import_failed", "failed", "media_import_completed", FAILURE_REASON),
        ("media_import_blocked", "blocked", None, FAILURE_REASON),
        ("media_action_failed", "failed", None, FAILURE_REASON),
        (
            "media_playback_failed",
            "failed",
            "media_playback_started",
            FAILURE_REASON,
        ),
        ("media_horizon_export_failed", "failed", None, FAILURE_REASON),
        (
            "note_recording_failed",
            "failed",
            "note_recording_completed",
            FAILURE_REASON,
        ),
        ("note_import_failed", "failed", "note_import_completed", FAILURE_REASON),
        (
            "note_processing_failed",
            "failed",
            "note_processing_completed",
            FAILURE_REASON,
        ),
        (
            "notes_setting_failed",
            "failed",
            "notes_setting_updated",
            FAILURE_REASON,
        ),
        ("note_export_failed", "failed", "note_export_completed", FAILURE_REASON),
        ("note_delete_failed", "failed", "note_deleted", FAILURE_REASON),
        (
            "note_speaker_label_blocked",
            "blocked",
            "note_speaker_label_evaluated",
            FAILURE_REASON,
        ),
        ("reminder_save_failed", "failed", "reminder_saved", FAILURE_REASON),
        (
            "reminder_playback_failed",
            "failed",
            "reminder_playback_started",
            FAILURE_REASON,
        ),
        (
            "translation_blocked",
            "blocked",
            None,
            "customEvent:block_reason",
        ),
        (
            "translation_session_failed",
            "failed",
            "translation_session_completed",
            FAILURE_REASON,
        ),
        (
            "tutorial_help_link_open_failed",
            "failed",
            "tutorial_help_link_opened",
            FAILURE_REASON,
        ),
    )
)


class ReportError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, help="Read fixed Data API responses from JSON.")
    parser.add_argument("--config", type=Path, help="Read local runtime configuration.")
    parser.add_argument("--preview", action="store_true", help="Print the Feishu payload.")
    parser.add_argument("--as-of", type=date.fromisoformat)
    return parser.parse_args()


def completed_weeks(as_of: date) -> tuple[tuple[date, date], tuple[date, date]]:
    current_end = as_of - timedelta(days=as_of.weekday() + 1)
    current_start = current_end - timedelta(days=6)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    return (current_start, current_end), (previous_start, previous_end)


def response_headers(response: Any) -> tuple[list[str], list[str]]:
    if not isinstance(response, dict):
        raise ReportError("Data API response is invalid")
    dimension_headers = response.get("dimensionHeaders")
    metric_headers = response.get("metricHeaders")
    if dimension_headers is None and isinstance(metric_headers, list):
        raw_rows = response.get("rows", [])
        if isinstance(raw_rows, list) and all(
            isinstance(row, dict) and not row.get("dimensionValues")
            for row in raw_rows
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


def parse_rows(
    response: Any, required_fields: set[str] | None = None
) -> list[dict[str, str]]:
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


def scalar_metric(response: dict[str, Any], metric: str) -> int:
    rows = parse_rows(response, {metric})
    return int(rows[0][metric]) if rows else 0


def load_fixture(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data.get("metadata"), dict) or not isinstance(
            data.get("reports"), dict
        ):
            raise ReportError("fixture must contain metadata and reports")
        return data
    except (OSError, json.JSONDecodeError) as error:
        raise ReportError("fixture could not be read") from error


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

    property_id = str(config.get("property_id", ""))
    if not property_id.isdigit():
        raise ReportError("config property_id must contain digits only")
    timezone_name = config.get("report_timezone", "")
    try:
        ZoneInfo(timezone_name)
    except (TypeError, ZoneInfoNotFoundError) as error:
        raise ReportError("config report_timezone is invalid") from error
    if config.get("environment") not in (None, "prod"):
        raise ReportError("config environment must be prod when set")
    return config


def report_date(config: dict[str, Any] | None, explicit: date | None) -> date:
    if explicit:
        return explicit
    if config:
        return datetime.now(ZoneInfo(config["report_timezone"])).date()
    return date.today()


@cache
def schema_contract() -> tuple[set[str], dict[str, dict[str, frozenset[str]]]]:
    schema_dir = Path(__file__).resolve().parents[1] / "analytics_schema"
    event_pattern = re.compile(r"^\s*- event_name:\s*([a-z0-9_]+)\s*$")
    schema_events: set[str] = set()
    allowed_values: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for path in schema_dir.glob("*.yaml"):
        current_event: str | None = None
        current_event_indent = -1
        current_param: str | None = None
        inside_allowed_values = False
        allowed_values_indent = -1
        for line in path.read_text(encoding="utf-8").splitlines():
            indent = len(line) - len(line.lstrip())
            match = event_pattern.match(line)
            if match:
                current_event = match.group(1)
                current_event_indent = indent
                schema_events.add(current_event)
                inside_allowed_values = False
                current_param = None
                continue
            stripped = line.strip()
            if (
                current_event
                and indent > current_event_indent
                and stripped == "allowed_values:"
            ):
                inside_allowed_values = True
                allowed_values_indent = indent
                current_param = None
                continue
            if not inside_allowed_values:
                continue
            if indent <= allowed_values_indent:
                inside_allowed_values = False
                current_param = None
                continue
            inline_values = re.match(r"^([a-z0-9_]+):\s*\[(.*)\]$", stripped)
            if inline_values:
                current_param = inline_values.group(1)
                for value in inline_values.group(2).split(","):
                    allowed_values[current_event][current_param].add(
                        value.strip().strip("'\"")
                    )
            elif stripped.endswith(":") and not stripped.startswith("- "):
                current_param = stripped[:-1]
            elif current_param and stripped.startswith("- "):
                value = stripped[2:].strip().strip("'\"")
                allowed_values[current_event][current_param].add(value)

    frozen_values = {
        event_name: {
            param: frozenset(values) for param, values in params.items()
        }
        for event_name, params in allowed_values.items()
    }
    return schema_events, frozen_values


def validate_rules_against_schema() -> None:
    schema_events, allowed_values = schema_contract()

    mapped_events = [rule.event_name for rule in OUTCOME_RULES]
    mapped_denominators = [
        rule.denominator_event for rule in OUTCOME_RULES if rule.denominator_event
    ]
    unknown = sorted((set(mapped_events) | set(mapped_denominators)) - schema_events)
    if len(mapped_events) != len(set(mapped_events)):
        raise ReportError("abnormal outcome mapping contains duplicate events")
    if unknown:
        raise ReportError("abnormal outcome mapping does not match the analytics schema")
    missing_reason_contract = [
        rule.event_name
        for rule in OUTCOME_RULES
        if not allowed_values.get(rule.event_name, {}).get(
            rule.reason_dimension.removeprefix("customEvent:")
        )
    ]
    if missing_reason_contract:
        raise ReportError("abnormal outcome reason mapping does not match the schema")


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
        raise ReportError(
            "personal ADC is unavailable; run gcloud auth application-default login"
        )
    return token


def data_api_base_url(config: dict[str, Any]) -> str:
    url = str(
        os.environ.get("GA4_DATA_API_BASE_URL")
        or config.get("data_api_base_url", "")
    ).rstrip("/")
    if not url:
        raise ReportError("Data API base URL is missing")
    if url.startswith("https://") or url.startswith(
        ("http://127.0.0.1:", "http://localhost:")
    ):
        return url
    raise ReportError("Data API base URL must use HTTPS")


def request_json(
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    encoded = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=encoded,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ReportError("Data API response is too large")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ReportError("Data API response is invalid")
            return payload
    except urllib.error.HTTPError as error:
        raise ReportError(f"Data API request failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ReportError("Data API request could not be completed") from error
    except json.JSONDecodeError as error:
        raise ReportError("Data API response is not valid JSON") from error


def feishu_webhook_url(config: dict[str, Any]) -> str:
    url = str(config.get("feishu_webhook_url", ""))
    parsed = urllib.parse.urlparse(url)
    is_loopback = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "localhost",
    }
    if parsed.scheme != "https" and not is_loopback:
        raise ReportError("Feishu Webhook URL must use HTTPS")
    if not parsed.netloc:
        raise ReportError("Feishu Webhook URL is invalid")
    return url


def send_feishu(card: dict[str, Any], config: dict[str, Any]) -> None:
    secret = config.get("feishu_secret")
    if not isinstance(secret, str) or not secret:
        raise ReportError("Feishu signing secret is missing")
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}".encode()
    sign = base64.b64encode(
        hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    ).decode()
    payload = {**card, "timestamp": timestamp, "sign": sign}
    request = urllib.request.Request(
        feishu_webhook_url(config),
        data=json.dumps(payload, ensure_ascii=False).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ReportError("Feishu response is too large")
            result = json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ReportError(f"Feishu delivery failed with HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ReportError("Feishu delivery could not be completed") from error
    except json.JSONDecodeError as error:
        raise ReportError("Feishu response is not valid JSON") from error
    if not isinstance(result, dict) or (
        result.get("code") != 0 and result.get("StatusCode") != 0
    ):
        raise ReportError("Feishu rejected the report")


def in_list_filter(field_name: str, values: list[str]) -> dict[str, Any]:
    return {
        "filter": {
            "fieldName": field_name,
            "inListFilter": {"values": values, "caseSensitive": True},
        }
    }


def report_filter(event_names: list[str], config: dict[str, Any]) -> dict[str, Any]:
    event_filter = in_list_filter("eventName", event_names)
    environment_filter = configured_environment_filter(config)
    if not environment_filter:
        return event_filter
    return {
        "andGroup": {
            "expressions": [
                event_filter,
                environment_filter,
            ]
        }
    }


def configured_environment_filter(
    config: dict[str, Any],
) -> dict[str, Any] | None:
    environment = config.get("environment")
    if not environment:
        return None
    return {
        "filter": {
            "fieldName": "customEvent:environment",
            "stringFilter": {
                "matchType": "EXACT",
                "value": environment,
                "caseSensitive": True,
            },
        }
    }


def run_report(
    base_url: str,
    property_id: str,
    token: str,
    period: tuple[date, date],
    dimensions: list[str],
    metrics: list[str],
    dimension_filter: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "dateRanges": [
            {"startDate": period[0].isoformat(), "endDate": period[1].isoformat()}
        ],
        "dimensions": [{"name": name} for name in dimensions],
        "metrics": [{"name": name} for name in metrics],
        # ponytail: weekly dimensions are low-cardinality; paginate if this limit is reached.
        "limit": "100000",
    }
    if dimension_filter:
        body["dimensionFilter"] = dimension_filter
    return request_json(
        "POST",
        f"{base_url}/properties/{property_id}:runReport",
        token,
        body,
    )


def fetch_period(
    base_url: str,
    config: dict[str, Any],
    token: str,
    period: tuple[date, date],
    metadata_dimensions: set[str],
) -> dict[str, Any]:
    property_id = str(config["property_id"])
    abnormal_names = [rule.event_name for rule in OUTCOME_RULES]
    outcome_names = sorted(
        set(abnormal_names)
        | {
            rule.denominator_event
            for rule in OUTCOME_RULES
            if rule.denominator_event
        }
    )
    environment_available = "customEvent:environment" in metadata_dimensions
    filter_config = config if environment_available else {**config, "environment": None}
    reports: dict[str, Any] = {
        "outcomes": run_report(
            base_url,
            property_id,
            token,
            period,
            ["eventName"],
            ["eventCount", "totalUsers"],
            report_filter(outcome_names, filter_config),
        ),
        "affected_users": run_report(
            base_url,
            property_id,
            token,
            period,
            [],
            ["totalUsers"],
            report_filter(abnormal_names, filter_config),
        ),
        "active_users": run_report(
            base_url,
            property_id,
            token,
            period,
            [],
            ["activeUsers"],
            configured_environment_filter(filter_config),
        ),
        "reasons": {},
    }
    for reason_dimension in sorted({rule.reason_dimension for rule in OUTCOME_RULES}):
        if reason_dimension not in metadata_dimensions:
            continue
        event_names = [
            rule.event_name
            for rule in OUTCOME_RULES
            if rule.reason_dimension == reason_dimension
        ]
        dimensions = ["eventName", reason_dimension]
        dimensions.extend(
            name for name in ("platform", "appVersion") if name in metadata_dimensions
        )
        reports["reasons"][reason_dimension] = run_report(
            base_url,
            property_id,
            token,
            period,
            dimensions,
            ["eventCount"],
            report_filter(event_names, filter_config),
        )
    return reports


def fetch_data_api(
    config: dict[str, Any], as_of: date
) -> dict[str, Any]:
    token = access_token(config)
    base_url = data_api_base_url(config)
    property_id = str(config["property_id"])
    metadata = request_json(
        "GET", f"{base_url}/properties/{property_id}/metadata", token
    )
    metadata_dimensions = {
        item.get("apiName", "") for item in metadata.get("dimensions", [])
    }
    current_period, previous_period = completed_weeks(as_of)
    warnings: list[str] = []
    if not config.get("environment"):
        warnings.append("未配置 environment，数据未按环境过滤")
    elif "customEvent:environment" not in metadata_dimensions:
        warnings.append("环境维度未注册，未应用 environment 过滤")
    missing_context = [
        dimension
        for dimension in ("platform", "appVersion")
        if dimension not in metadata_dimensions
    ]
    if missing_context:
        warnings.append("原因上下文维度不可用：" + "、".join(missing_context))
    return {
        "metadata": metadata,
        "warnings": warnings,
        "reports": {
            "current": fetch_period(
                base_url, config, token, current_period, metadata_dimensions
            ),
            "previous": fetch_period(
                base_url, config, token, previous_period, metadata_dimensions
            ),
        },
    }


def percent_change(current: int, previous: int) -> str:
    if previous == 0:
        return "new" if current else "0.0%"
    return f"{(current - previous) / previous * 100:+.1f}%"


def calculate_rate(
    rule: OutcomeRule, event_count: int, outcomes: dict[str, dict[str, int]]
) -> tuple[float, int] | None:
    if not rule.denominator_event:
        return None
    denominator_count = outcomes.get(rule.denominator_event, {}).get("eventCount", 0)
    if rule.outcome_type == "blocked":
        denominator = denominator_count
    else:
        denominator = denominator_count + event_count
    return (event_count / denominator, denominator) if denominator else None


def outcome_values(response: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        row["eventName"]: {
            "eventCount": int(row["eventCount"]),
            "totalUsers": int(row["totalUsers"]),
        }
        for row in parse_rows(response, {"eventName", "eventCount", "totalUsers"})
    }


def reason_values(
    reports: dict[str, Any],
) -> tuple[dict[str, list[dict[str, str | int]]], int]:
    _, schema_allowed_values = schema_contract()
    rules_by_event = {rule.event_name: rule for rule in OUTCOME_RULES}
    grouped: dict[str, dict[str, dict[tuple[str, str], int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    hidden_unapproved = 0
    for reason_dimension, response in reports.items():
        for row in parse_rows(
            response, {"eventName", reason_dimension, "eventCount"}
        ):
            event_name = row["eventName"]
            rule = rules_by_event.get(event_name)
            reason = row.get(reason_dimension, "")
            if reason in {"", "(not set)"}:
                continue
            count = int(row["eventCount"])
            reason_param = reason_dimension.removeprefix("customEvent:")
            approved_values = schema_allowed_values.get(event_name, {}).get(
                reason_param, frozenset()
            )
            if not rule or rule.reason_dimension != reason_dimension or reason not in approved_values:
                hidden_unapproved += count
                continue
            context = (row.get("platform", "unknown"), row.get("appVersion", "unknown"))
            grouped[event_name][reason][context] += count

    result: dict[str, list[dict[str, str | int]]] = {}
    for event_name, event_reasons in grouped.items():
        values: list[dict[str, str | int]] = []
        for reason, contexts in event_reasons.items():
            (platform, app_version), context_count = min(
                contexts.items(), key=lambda item: (-item[1], item[0])
            )
            values.append(
                {
                    "reason": reason,
                    "platform": platform,
                    "app_version": app_version,
                    "context_count": context_count,
                    "event_count": sum(contexts.values()),
                }
            )
        result[event_name] = sorted(
            values, key=lambda item: (-int(item["event_count"]), str(item["reason"]))
        )
    return result, hidden_unapproved


def text_element(content: str) -> dict[str, Any]:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def build_failure_card(as_of: date) -> dict[str, Any]:
    current_period, _ = completed_weeks(as_of)
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "red",
                "title": {
                    "tag": "plain_text",
                    "content": "GA4 业务异常周报生成失败",
                },
            },
            "elements": [
                text_element(
                    "本次周报未生成成功，请查看本地脱敏日志。\n"
                    f"计划周期：{current_period[0].isoformat()}～"
                    f"{current_period[1].isoformat()}"
                )
            ],
        },
    }


def build_card(report_data: dict[str, Any], as_of: date) -> dict[str, Any]:
    (current_start, current_end), (previous_start, previous_end) = completed_weeks(as_of)
    reports = report_data["reports"]
    current = reports["current"]
    previous = reports["previous"]
    current_outcomes = outcome_values(current["outcomes"])
    previous_outcomes = outcome_values(previous["outcomes"])
    reasons, hidden_unapproved = reason_values(current.get("reasons", {}))

    abnormal_events: list[dict[str, Any]] = []
    for rule in OUTCOME_RULES:
        current_values = current_outcomes.get(
            rule.event_name, {"eventCount": 0, "totalUsers": 0}
        )
        previous_values = previous_outcomes.get(
            rule.event_name, {"eventCount": 0, "totalUsers": 0}
        )
        if current_values["eventCount"] == 0:
            continue
        abnormal_events.append(
            {
                "rule": rule,
                "event_count": current_values["eventCount"],
                "total_users": current_values["totalUsers"],
                "previous_event_count": previous_values["eventCount"],
                "rate": calculate_rate(
                    rule, current_values["eventCount"], current_outcomes
                ),
                "previous_rate": calculate_rate(
                    rule, previous_values["eventCount"], previous_outcomes
                ),
            }
        )
    abnormal_events.sort(key=lambda item: (-item["event_count"], item["rule"].event_name))

    total_abnormal = sum(item["event_count"] for item in abnormal_events)
    previous_total = sum(
        previous_outcomes.get(rule.event_name, {}).get("eventCount", 0)
        for rule in OUTCOME_RULES
    )
    affected_users = scalar_metric(current["affected_users"], "totalUsers")
    previous_affected = scalar_metric(previous["affected_users"], "totalUsers")
    active_users = scalar_metric(current["active_users"], "activeUsers")

    overall = (
        "**总体**\n"
        f"异常事件：{total_abnormal:,}（上周 {previous_total:,}，"
        f"{percent_change(total_abnormal, previous_total)}）\n"
        f"影响用户：{affected_users:,}（上周 {previous_affected:,}）\n"
        f"活跃用户：{active_users:,}\n"
        f"对比周期：{previous_start.isoformat()}～{previous_end.isoformat()}"
    )

    event_lines = ["**异常事件 Top 10**"]
    if not abnormal_events:
        event_lines.append("本周未检测到白名单业务异常事件")
    for index, item in enumerate(abnormal_events[:10], start=1):
        rule = item["rule"]
        line = (
            f"{index}. `{rule.event_name}` — {item['event_count']:,} 次，"
            f"{item['total_users']:,} 用户；次数环比 "
            f"{percent_change(item['event_count'], item['previous_event_count'])}"
        )
        label = {
            "failed": "失败率",
            "blocked": "阻断率",
            "degraded": "降级率",
        }.get(rule.outcome_type, "结果率")
        if item["rate"]:
            rate, denominator = item["rate"]
            line += f"；{label} {rate * 100:.1f}%（{item['event_count']}/{denominator}）"
            if item["previous_rate"]:
                delta = (rate - item["previous_rate"][0]) * 100
                line += f"，较上周 {delta:+.1f} pp"
            else:
                line += "，较上周 unavailable"
        elif rule.denominator_event:
            line += f"；{label} unavailable（分母为 0）"
        elif active_users:
            per_thousand = item["event_count"] / active_users * 1000
            line += f"；每千活跃用户 {per_thousand:.1f} 次"
        else:
            line += "；每千活跃用户 unavailable（活跃用户为 0）"
        event_lines.append(line)

    metadata_dimensions = {
        item.get("apiName", "")
        for item in report_data["metadata"].get("dimensions", [])
    }
    reason_lines = ["**主要原因**"]
    if not abnormal_events:
        reason_lines.append("本周无异常原因需要拆解")
    for item in abnormal_events[:10]:
        rule = item["rule"]
        event_name = rule.event_name
        if rule.reason_dimension not in metadata_dimensions:
            reason_lines.append(
                f"`{event_name}` 覆盖率 unavailable（原因维度未注册）"
            )
            continue
        event_reasons = reasons.get(event_name, [])
        covered = sum(int(reason["event_count"]) for reason in event_reasons)
        coverage = covered / item["event_count"] * 100 if item["event_count"] else 0
        reason_lines.append(f"`{event_name}` 覆盖率 {coverage:.1f}%")
        for reason in event_reasons[:3]:
            share = int(reason["event_count"]) / item["event_count"] * 100
            reason_lines.append(
                f"• {reason['reason']}：{reason['event_count']}（{share:.1f}%）；"
                f"最高上下文 {reason['platform']} / {reason['app_version']}："
                f"{reason['context_count']}"
            )

    missing_dimensions = sorted(
        {
            rule.reason_dimension
            for rule in OUTCOME_RULES
            if rule.reason_dimension not in metadata_dimensions
        }
    )
    quality_lines = ["**数据质量**"]
    quality_lines.append(
        "未注册原因维度：" + "、".join(missing_dimensions)
        if missing_dimensions
        else "自定义原因维度均可查询"
    )
    quality_lines.extend(report_data.get("warnings", []))
    if hidden_unapproved:
        quality_lines.append(f"已隐藏未批准原因值：{hidden_unapproved} 次")
    quality = "\n".join(quality_lines)

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": (
                        f"GA4 业务异常周报｜{current_start.isoformat()}～"
                        f"{current_end.isoformat()}"
                    ),
                },
            },
            "elements": [
                text_element(overall),
                {"tag": "hr"},
                text_element("\n".join(event_lines)),
                {"tag": "hr"},
                text_element("\n".join(reason_lines)),
                {"tag": "hr"},
                text_element(quality),
            ],
        },
    }


def notify_generation_failure(
    config: dict[str, Any] | None, as_of: date, preview: bool
) -> None:
    if not config or preview:
        return
    try:
        send_feishu(build_failure_card(as_of), config)
    except ReportError:
        print(
            "error: Feishu failure notification could not be delivered",
            file=sys.stderr,
        )


def main() -> int:
    args = parse_args()
    config: dict[str, Any] | None = None
    as_of = args.as_of or date.today()
    try:
        validate_rules_against_schema()
        config = load_config(args.config) if args.config else None
        if not args.fixture and not config:
            raise ReportError("--config is required for live GA4 mode")
        as_of = report_date(config, args.as_of)
        data = load_fixture(args.fixture) if args.fixture else fetch_data_api(config, as_of)
        card = build_card(data, as_of)
    except (ReportError, KeyError, TypeError, ValueError, AttributeError) as error:
        notify_generation_failure(config, as_of, args.preview)
        message = str(error) if isinstance(error, ReportError) else "report response is invalid"
        print(f"error: {message}", file=sys.stderr)
        return 1

    if args.preview:
        print(json.dumps(card, ensure_ascii=False, separators=(",", ":")))
        return 0
    if not config:
        print("error: --config is required for Feishu delivery", file=sys.stderr)
        return 1
    try:
        send_feishu(card, config)
    except ReportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("sent GA4 weekly abnormal-outcome report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
