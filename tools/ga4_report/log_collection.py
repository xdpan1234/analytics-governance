"""UTC daily-export facts and bounded collection proposals; no task creation or push IO."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .rules import OutcomeRule, schema_contract

APPLICATION_ID = "ai.looktech.glasses.memo"
STREAM_IDS = frozenset({"12211280819", "12211302713"})


@dataclass(frozen=True)
class CollectionPolicy:
    key_records: int = 1
    sdk_records: int = 2
    network_records: int = 3
    impact_accounts: int = 3
    noisy_account_records: int = 10
    maximum_accounts: int = 20
    maximum_per_group: int = 3
    maximum_age_hours: int = 168

    def __post_init__(self) -> None:
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in vars(self).values()):
            raise ValueError("Collection limits must be positive")


@dataclass(frozen=True)
class CollectionRow:
    day: date
    event_name: str
    platform: str
    version: str
    account_id: str | None
    reason: str | None
    records: int
    last_at: datetime
    routing_valid: bool
    error_source: str | None = None
    sync_state: str | None = None
    analytics_user_id: str | None = None
    account_status: str = "VALID"

    @property
    def group(self) -> tuple[str, ...]:
        if self.event_name == "device_usage_media_sync_failed":
            return (self.event_name, self.platform, self.error_source or "MISSING_SOURCE",
                    self.reason or "MISSING_PARAMETER")
        return self.event_name, self.platform, self.reason or "MISSING_PARAMETER"


SDK_REASONS = frozenset({"sdk_error", "unknown", "unsupported_state", "app_error", "upload_failed", "media_sync_failed"})
NETWORK_REASONS = frozenset({"network_error", "timeout", "session_ready_timeout", "rtc_join_failed", "session_init_failed", "translation_failed"})
EXPECTED_REASONS = frozenset({
    "cancelled", "canceled", "user_cancelled", "permission_denied", "device_not_connected", "not_connected",
    "network_unavailable", "no_network", "low_battery", "device_busy", "busy", "short_recording", "audio_too_short",
    "unauthorized", "not_logged_in",
})
EXPECTED_EVENT_REASONS = {
    "account_username_rule_blocked": frozenset({"validation_failed"}),
    "note_import_failed": frozenset({"file_too_short"}),
    "translation_blocked": frozenset({
        "their_language_missing", "same_language_pair", "saved_config_missing", "glasses_not_connected", "credits_used_up",
    }),
}


def _is_expected(row: CollectionRow) -> bool:
    return row.reason in EXPECTED_REASONS or row.reason in EXPECTED_EVENT_REASONS.get(row.event_name, ())


def utc_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(), UTC)
    return start, start + timedelta(days=1)


def required_tables(day: date, property_timezone: str = "Asia/Shanghai") -> frozenset[str]:
    start, end = utc_window(day)
    timezone = ZoneInfo(property_timezone)
    first = start.astimezone(timezone).date()
    last = (end - timedelta(microseconds=1)).astimezone(timezone).date()
    return frozenset(f"events_{(first + timedelta(days=i)):%Y%m%d}" for i in range((last - first).days + 1))


def ready_days(days: Iterable[date], tables: set[str], property_timezone: str) -> set[date]:
    return {day for day in days if required_tables(day, property_timezone) <= tables}


def build_query(dataset: str, start: date, end: date, tables: set[str], rules: tuple[OutcomeRule, ...],
                property_timezone: str = "Asia/Shanghai") -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+\.[a-zA-Z0-9_]+", dataset) or end < start:
        raise ValueError("Invalid dataset or UTC interval")
    wanted = set().union(*(required_tables(start + timedelta(days=i), property_timezone) for i in range((end - start).days + 1)))
    suffixes = sorted(table.removeprefix("events_") for table in wanted & tables if re.fullmatch(r"events_[0-9]{8}", table))
    if not suffixes:
        raise ValueError("No daily export tables are available")
    events = {rule.event_name for rule in rules} | {rule.denominator_event for rule in rules if rule.denominator_event}
    events.add("app_previous_process_exit")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name) for name in events):
        raise ValueError("Invalid event name in rules")
    names = ", ".join(repr(name) for name in sorted(events))
    suffix_sql = ", ".join(repr(value) for value in suffixes)
    routing = ("environment", "build_region", "build_type", "failure_reason", "block_reason", "error_source", "sync_state")
    fields = routing + ("exit_reason",)
    extracts = ",\n    ".join(
        f"(SELECT MAX(value.string_value) FROM UNNEST(event_params) WHERE key='{name}') AS {name}" for name in fields
    )
    routing_sql = ", ".join(repr(value) for value in fields)
    return f"""WITH source AS (
    SELECT DATE(TIMESTAMP_MICROS(event_timestamp), 'UTC') AS utc_day,
    event_name, LOWER(platform) AS platform, app_info.version AS app_version, app_info.id AS app_id,
    stream_id, user_id, user_pseudo_id, event_timestamp,
    {extracts},
    (SELECT COUNT(*) - COUNT(DISTINCT key) FROM UNNEST(event_params)
      WHERE key IN ({routing_sql})) AS duplicate_keys
  FROM `{dataset}.events_*`
  WHERE _TABLE_SUFFIX IN ({suffix_sql})
    AND event_timestamp >= UNIX_MICROS(TIMESTAMP('{start.isoformat()} 00:00:00+00'))
    AND event_timestamp < UNIX_MICROS(TIMESTAMP('{(end + timedelta(days=1)).isoformat()} 00:00:00+00'))
    AND event_name IN ({names})
    AND app_info.id='{APPLICATION_ID}'
    AND stream_id IN ({', '.join(repr(item) for item in sorted(STREAM_IDS))})
)
SELECT utc_day, event_name, platform, app_version, app_id, stream_id, user_id, user_pseudo_id, environment, build_region, build_type,
  failure_reason, block_reason, error_source, sync_state, exit_reason,
  duplicate_keys, COUNT(*) AS records, MIN(event_timestamp) AS first_us, MAX(event_timestamp) AS last_us
FROM source
WHERE environment='prod' AND build_region='us' AND build_type='release'
GROUP BY utc_day, event_name, platform, app_version, app_id, stream_id, user_id, user_pseudo_id, environment, build_region, build_type,
  failure_reason, block_reason, error_source, sync_state, exit_reason, duplicate_keys
ORDER BY utc_day, event_name, platform"""


def parse_rows(raw_rows: list[dict[str, Any]], rules: tuple[OutcomeRule, ...]) -> list[CollectionRow]:
    by_name = {rule.event_name: rule for rule in rules}
    rows = []
    for raw in raw_rows:
        if not {"app_id", "stream_id", "environment", "build_region", "build_type", "user_pseudo_id", "duplicate_keys"} <= raw.keys():
            raise ValueError("Collection rows must include the verified application and routing scope")
        if (raw["app_id"] != APPLICATION_ID or str(raw["stream_id"]) not in STREAM_IDS or
                (raw["environment"], raw["build_region"], raw["build_type"]) != ("prod", "us", "release")):
            continue
        name = str(raw["event_name"])
        if name not in by_name and name != "app_previous_process_exit":
            # Successful denominator events stay in the report, but never become candidates.
            if name not in {rule.denominator_event for rule in rules}:
                continue
        dimension = by_name[name].reason_dimension.split(":")[-1] if name in by_name else "exit_reason"
        if dimension == "error_source":
            dimension = "failure_reason"
        account = str(raw.get("user_id") or "")
        account_status = "VALID" if account else "MISSING_ACCOUNT"
        if not re.fullmatch(r"[1-9][0-9]*", account) or int(account) > 2**63 - 1:
            account_status = "INVALID_ACCOUNT" if account else "MISSING_ACCOUNT"
            account = None
        count = int(raw["records"])
        if count <= 0:
            raise ValueError("Record counts must be positive")
        last = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(raw["last_us"]))
        day = date.fromisoformat(str(raw["utc_day"]))
        if last.date() != day:
            raise ValueError("Aggregated rows must be grouped by UTC day")
        reason = raw.get(dimension)
        rows.append(CollectionRow(day, name, str(raw["platform"]).lower(), str(raw.get("app_version") or ""),
                                  account, str(reason) if reason is not None else None, count, last,
                                  int(raw.get("duplicate_keys", 0)) == 0, raw.get("error_source"), raw.get("sync_state"),
                                  raw.get("user_pseudo_id"), account_status))
    return rows


def _reason_issue(row: CollectionRow, rule: OutcomeRule | None,
                  contracts: dict[str, dict[str, frozenset[str]]]) -> str | None:
    if not row.reason:
        return "MISSING_REASON"
    if row.event_name == "app_previous_process_exit":
        return None if row.reason in {"crash", "anr"} else "NON_CRASH_EXIT"
    dimension = rule.reason_dimension.split(":")[-1] if rule else "exit_reason"
    contract = contracts.get(row.event_name, {})
    if dimension == "error_source":
        dimension = "failure_reason"
        if not row.error_source or not row.sync_state:
            return "MISSING_MEDIA_CONTEXT"
        if row.error_source not in contract.get("error_source", ()) or row.sync_state not in contract.get("sync_state", ()):
            return "INVALID_MEDIA_CONTEXT"
    return None if row.reason in contract.get(dimension, ()) else "INVALID_REASON"


def _reason_allowed(row: CollectionRow, rule: OutcomeRule | None,
                    contracts: dict[str, dict[str, frozenset[str]]]) -> bool:
    return (_reason_issue(row, rule, contracts) is None and
            (row.event_name != "app_previous_process_exit" or row.reason in {"crash", "anr"}))


def _result_rate(rule: OutcomeRule, records: int, completed: int, ambiguous: int) -> dict[str, Any]:
    total = completed + records if rule.outcome_type in {"failed", "degraded"} else completed
    status = ("UNAVAILABLE_NO_DENOMINATOR" if not rule.denominator_event else
              "UNAVAILABLE_AMBIGUOUS_PARAMETERS" if ambiguous else
              "UNAVAILABLE_ZERO_DENOMINATOR" if total == 0 else
              "UNAVAILABLE_INCONSISTENT_DENOMINATOR" if records > total else "AVAILABLE")
    return {"result_rate": records / total if status == "AVAILABLE" else None, "result_rate_status": status}


def _entry_rules(row: CollectionRow, rule: OutcomeRule | None, top10: set[str], group_accounts: int,
                 group_records: int, policy: CollectionPolicy) -> list[str]:
    if _is_expected(row) or not row.routing_valid:
        return []
    entries = []
    critical = row.event_name == "app_previous_process_exit" or row.event_name == "note_processing_failed" or row.reason in {"decode_error", "file_missing"}
    if critical and row.records >= policy.key_records:
        entries.append("KEY_SIGNAL")
    if row.reason in SDK_REASONS and row.records >= policy.sdk_records:
        entries.append("SDK_OR_UNKNOWN")
    if row.reason in NETWORK_REASONS and row.records >= policy.network_records:
        entries.append("NETWORK_OR_TIMEOUT")
    unexpected_outcome = rule is not None
    if unexpected_outcome and row.event_name in top10 and group_accounts >= policy.impact_accounts:
        entries.append("TOP10_IMPACT")
    if unexpected_outcome and row.records >= policy.noisy_account_records and row.records * 2 >= group_records:
        entries.append("SINGLE_ACCOUNT_NOISE")
    return entries


def build_daily_report(day: date, rows: list[CollectionRow], rules: tuple[OutcomeRule, ...],
                       contracts: dict[str, dict[str, frozenset[str]]] | None = None) -> dict[str, Any]:
    contracts = contracts if contracts is not None else schema_contract()[1]
    selected = [row for row in rows if row.day == day]
    counts = Counter()
    accounts: dict[str, set[str]] = defaultdict(set)
    analytics_users: dict[str, set[str]] = defaultdict(set)
    unidentified_analytics_users: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    failures: dict[str, Counter[str]] = defaultdict(Counter)
    breakdowns: dict[str, Counter[tuple[str, str]]] = {"platform": Counter(), "version": Counter()}
    rule_map = {rule.event_name: rule for rule in rules}
    issues: dict[str, Counter[str]] = defaultdict(Counter)
    ambiguous: Counter[str] = Counter()
    ambiguous_breakdowns: dict[str, Counter[tuple[str, str]]] = {"platform": Counter(), "version": Counter()}
    for row in selected:
        if not row.routing_valid:
            ambiguous[row.event_name] += row.records
            ambiguous_breakdowns["platform"][row.event_name, row.platform] += row.records
            ambiguous_breakdowns["version"][row.event_name, row.version] += row.records
            continue
        counts[row.event_name] += row.records
        if row.account_id:
            accounts[row.event_name].add(row.account_id)
        if row.analytics_user_id:
            analytics_users[row.event_name].add(row.analytics_user_id)
        else:
            unidentified_analytics_users[row.event_name] += row.records
        breakdowns["platform"][row.event_name, row.platform] += row.records
        breakdowns["version"][row.event_name, row.version] += row.records
        rule = rule_map.get(row.event_name)
        if row.account_id is None:
            issues[row.event_name][row.account_status if row.account_status != "VALID" else "MISSING_ACCOUNT"] += row.records
        if not row.analytics_user_id:
            issues[row.event_name]["MISSING_ANALYTICS_USER"] += row.records
        if row.platform not in {"android", "ios"}:
            issues[row.event_name]["UNSUPPORTED_PLATFORM"] += row.records
        if not row.version:
            issues[row.event_name]["MISSING_VERSION"] += row.records
        issue = None
        if rule or row.event_name == "app_previous_process_exit":
            issue = _reason_issue(row, rule, contracts)
            if issue:
                issues[row.event_name][issue] += row.records
            elif row.reason == "unknown":
                issues[row.event_name]["APPROVED_UNKNOWN"] += row.records
        reason = row.error_source if rule and rule.reason_dimension == "customEvent:error_source" else row.reason
        if issue:
            reason = issue
        reasons[row.event_name][reason or "MISSING_PARAMETER"] += row.records
        failures[row.event_name][issue or row.reason or "MISSING_PARAMETER"] += row.records
    metrics = []
    for rule in rules:
        numerator = counts[rule.event_name]
        denominator = counts[rule.denominator_event] if rule.denominator_event else 0
        ambiguous_records = ambiguous[rule.event_name] + ambiguous[rule.denominator_event]
        metrics.append({"event_name": rule.event_name, "records": numerator, "identified_accounts": len(accounts[rule.event_name]),
                        "analytics_users": len(analytics_users[rule.event_name]),
                        "unidentified_analytics_user_records": unidentified_analytics_users[rule.event_name],
                        "outcome_type": rule.outcome_type, "denominator_event": rule.denominator_event,
                        "denominator_records": denominator, **_result_rate(rule, numerator, denominator, ambiguous_records),
                        "quality": {"ambiguous_parameter_records": ambiguous[rule.event_name],
                                    "issues": dict(sorted(issues[rule.event_name].items()))},
                        "failure_reasons": [{"reason": reason, "records": count} for reason, count in failures[rule.event_name].most_common(3)],
                        "top_reasons": [{"reason": reason, "records": count} for reason, count in reasons[rule.event_name].most_common(3)]})
        for dimension, values in breakdowns.items():
            details = []
            for value in sorted({value for (name, value) in values if name == rule.event_name}):
                records = values[rule.event_name, value]
                completed = values[rule.denominator_event, value] if rule.denominator_event else 0
                details.append({dimension: value, "records": records, "denominator_records": completed,
                                **_result_rate(rule, records, completed,
                                    ambiguous_breakdowns[dimension][rule.event_name, value] +
                                    ambiguous_breakdowns[dimension][rule.denominator_event, value])})
            metrics[-1][dimension + "_breakdown"] = details
    metrics.sort(key=lambda item: (-item["records"], item["event_name"]))
    quality_issues = sum(issues.values(), Counter())
    quality_issues["AMBIGUOUS_PARAMETERS"] += sum(ambiguous.values())
    status = "NO_DATA" if not selected else "DEGRADED" if any(
        count for issue, count in quality_issues.items() if issue not in {"APPROVED_UNKNOWN", "NON_CRASH_EXIT"}) else "AVAILABLE"
    return {"statistical_day": day.isoformat(), "timezone": "UTC",
            "top10": [item for item in metrics if item["records"] > 0][:10], "events": metrics,
            "diagnostic_signals": counts["app_previous_process_exit"],
            "ambiguous_routing_records": sum(ambiguous.values()),
            "quality": {"status": status, "input_records": sum(row.records for row in selected),
                        "accepted_records": sum(counts.values()), "issues": dict(sorted(quality_issues.items())),
                        "count_basis": "EXPORTED_EVENT_RECORDS", "late_data_possible": True}}


def _candidate_issue(row: CollectionRow, rule: OutcomeRule | None,
                     contracts: dict[str, dict[str, frozenset[str]]], now: datetime,
                     policy: CollectionPolicy) -> str | None:
    if not row.routing_valid:
        return "AMBIGUOUS_PARAMETERS"
    if row.platform not in {"android", "ios"}:
        return "UNSUPPORTED_PLATFORM"
    issue = _reason_issue(row, rule, contracts)
    if issue:
        return issue
    if _is_expected(row):
        return "EXPECTED_BEHAVIOR"
    if row.account_id is None:
        return row.account_status if row.account_status != "VALID" else "MISSING_ACCOUNT"
    age = now.astimezone(UTC) - row.last_at
    return "FUTURE_EVENT" if age < timedelta(0) else "STALE_EVENT" if age > timedelta(hours=policy.maximum_age_hours) else None


def _excluded_observation(row: CollectionRow, reason: str) -> dict[str, Any]:
    # Invalid free-text reasons are never copied into output evidence.
    return {"account_id": row.account_id, "statistical_day": row.day.isoformat(),
            "event_name": row.event_name, "platform": row.platform, "records": row.records,
            "last_event_at": row.last_at.isoformat(), "reason": reason}


def build_candidates(day: date, rows: list[CollectionRow], rules: tuple[OutcomeRule, ...], now: datetime,
                     rules_version: str, policy: CollectionPolicy | None = None,
                     contracts: dict[str, dict[str, frozenset[str]]] | None = None,
                     exclusions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if now.tzinfo is None:
        raise ValueError("The selection clock must include a timezone")
    policy = policy or CollectionPolicy()
    contracts = contracts if contracts is not None else schema_contract()[1]
    rule_map = {rule.event_name: rule for rule in rules}
    exclusions = exclusions if exclusions is not None else []
    report = build_daily_report(day, rows, rules, contracts)
    top10 = {item["event_name"] for item in report["top10"] if item["records"] > 0}
    groups: dict[tuple[str, ...], list[CollectionRow]] = defaultdict(list)
    for row in rows:
        if row.day != day or (row.event_name not in rule_map and row.event_name != "app_previous_process_exit"):
            continue
        if row.routing_valid and row.platform in {"android", "ios"} and _reason_allowed(row, rule_map.get(row.event_name), contracts):
            groups[row.group].append(row)
        else:
            exclusions.append(_excluded_observation(row, _candidate_issue(row, rule_map.get(row.event_name), contracts, now, policy)))
    proposed = []
    for group, members in groups.items():
        population = {row.account_id for row in members if row.account_id}
        group_count = sum(row.records for row in members)
        per_account: dict[str, list[CollectionRow]] = defaultdict(list)
        for row in members:
            if row.account_id:
                per_account[row.account_id].append(row)
            else:
                exclusions.append(_excluded_observation(row, _candidate_issue(row, rule_map.get(row.event_name), contracts, now, policy)))
        for account, account_rows in per_account.items():
            last = max(row.last_at for row in account_rows)
            exemplar = account_rows[0]
            aggregate = CollectionRow(day, exemplar.event_name, exemplar.platform, exemplar.version, account,
                                      exemplar.reason, sum(row.records for row in account_rows), last, True,
                                      exemplar.error_source, exemplar.sync_state)
            issue = _candidate_issue(aggregate, rule_map.get(aggregate.event_name), contracts, now, policy)
            if issue:
                exclusions.append(_excluded_observation(aggregate, issue))
                continue
            entries = _entry_rules(aggregate, rule_map.get(aggregate.event_name), top10, len(population), group_count, policy)
            if not entries:
                exclusions.append(_excluded_observation(aggregate, "BELOW_THRESHOLD"))
                continue
            key = json.dumps(["prod", "us", account, aggregate.platform, day.isoformat(), list(group)], separators=(",", ":"))
            proposed.append({"candidate_key": hashlib.sha256(key.encode()).hexdigest(), "account_id": account,
                             "platform": aggregate.platform, "statistical_day": day.isoformat(), "group": list(group),
                             "environment": "prod", "region": "us", "sources": ["APP"], "rule_version": rules_version,
                             "matched_rules": entries, "records": aggregate.records, "group_accounts": len(population),
                             "group_records": group_count, "account_share": aggregate.records / group_count,
                             "evidence": {"event_name": aggregate.event_name, "failure_reason": aggregate.reason,
                                          "error_source": aggregate.error_source,
                                          "sync_states": sorted({row.sync_state for row in account_rows if row.sync_state})},
                             "last_event_at": last.isoformat(), "app_versions": sorted({row.version for row in account_rows}),
                             "priority": 0 if "KEY_SIGNAL" in entries else 1,
                             "priority_reason": "KEY_SIGNAL" if "KEY_SIGNAL" in entries else "STANDARD_RULE",
                             "disposition": "PROPOSED"})
    return proposed


def select_proposals(proposed: list[dict[str, Any]], policy: CollectionPolicy) -> list[dict[str, Any]]:
    proposed = sorted(proposed, key=lambda item: (item["priority"], -item["group_accounts"],
                      -datetime.fromisoformat(item["last_event_at"]).timestamp(), item["candidate_key"]))
    chosen = []
    selected_accounts: set[str] = set()
    per_group: Counter[tuple[str, ...]] = Counter()
    for priority in sorted({item["priority"] for item in proposed}):
        for round_number in range(policy.maximum_per_group):
            for candidate in proposed:
                group = tuple(candidate["group"])
                if candidate["priority"] != priority or candidate["account_id"] in selected_accounts or per_group[group] != round_number:
                    continue
                if len(selected_accounts) >= policy.maximum_accounts:
                    break
                chosen.append(dict(candidate)); selected_accounts.add(candidate["account_id"]); per_group[group] += 1
    for candidate in chosen:
        candidate["related_observations"] = [
            {key: item[key] for key in ("candidate_key", "group", "platform", "statistical_day", "matched_rules", "records")}
            for item in proposed if item["account_id"] == candidate["account_id"]
        ]
    return chosen


def _metric_issue(event: dict[str, Any], field: str) -> str | None:
    if event["quality"]["ambiguous_parameter_records"]:
        return "AMBIGUOUS_PARAMETERS"
    if field == "identified_accounts" and any(event["quality"]["issues"].get(key) for key in ("MISSING_ACCOUNT", "INVALID_ACCOUNT")):
        return "INCOMPLETE_ACCOUNT_COVERAGE"
    return event["result_rate_status"] if field == "result_rate" and event[field] is None else None


def _compare_metrics(current: dict[str, Any], references: list[dict[str, Any]], expected_days: int,
                     missing_status: str) -> dict[str, Any]:
    comparison = {}
    for field in ("records", "identified_accounts", "result_rate"):
        issue = _metric_issue(current, field)
        values = [item[field] for item in references if _metric_issue(item, field) is None]
        reference = median(values) if values else None
        status = ("UNAVAILABLE_CURRENT_METRIC" if issue else
                  missing_status if not references else "UNAVAILABLE_REFERENCE_METRIC" if not values else
                  "PARTIAL_BASELINE" if len(values) < expected_days else "AVAILABLE")
        delta = current[field] - reference if not issue and reference is not None else None
        relative = delta / reference if delta is not None and reference else 0.0 if delta == 0 else None
        comparison[field] = {
            "current": current[field], "reference": reference, "status": status,
            "unavailable_reason": issue if issue else status if status.startswith("UNAVAILABLE") else None,
            "delta": delta, "relative_change": relative,
            "change_status": "NEW" if delta is not None and current[field] > 0 and len(values) == expected_days and not any(values) else
                             "ZERO_REFERENCE" if delta is not None and reference == 0 and current[field] > 0 else
                             "AVAILABLE" if delta is not None else "NOT_COMPARABLE",
            "reference_days": len(values), "expected_reference_days": expected_days,
        }
        if field == "result_rate":
            comparison[field]["delta_percentage_points"] = delta * 100 if delta is not None else None
    return comparison


def build_collection_result(raw_rows: list[dict[str, Any]], available_tables: set[str], target_day: date,
                            now: datetime, rules: tuple[OutcomeRule, ...], rules_version: str,
                            property_timezone: str = "Asia/Shanghai", policy: CollectionPolicy | None = None) -> dict[str, Any]:
    policy = policy or CollectionPolicy()
    if now.tzinfo is None:
        raise ValueError("The selection clock must include a timezone")
    rows = parse_rows(raw_rows, rules)
    contracts = schema_contract()[1]
    coverage = []
    for offset in range(14):
        day = target_day - timedelta(days=offset)
        required = required_tables(day, property_timezone)
        missing = required - available_tables
        coverage.append({"statistical_day": day.isoformat(), "required_tables": sorted(required),
                         "missing_tables": sorted(missing), "status": "WAITING_EXPORT" if missing else "AVAILABLE"})
    recent = [target_day - timedelta(days=i) for i in range(7)]
    available = ready_days(recent, available_tables, property_timezone)
    latest = max(available) if available else None
    days = {day for day in recent[:4] if day in available}
    if latest:
        days.add(latest)
    reports = []
    candidates = []
    exclusions: list[dict[str, Any]] = []
    daily = {date.fromisoformat(item["statistical_day"]): build_daily_report(
        date.fromisoformat(item["statistical_day"]), rows, rules, contracts)
        for item in coverage if item["status"] == "AVAILABLE"}
    for day in sorted(days, reverse=True):
        report = dict(daily[day], events=[dict(item) for item in daily[day]["events"]])
        report["top10"] = [item for item in report["events"] if item["records"] > 0][:10]
        previous = day - timedelta(days=1)
        baseline = [day - timedelta(days=i) for i in range(1, 8)]
        comparable = ready_days(baseline, available_tables, property_timezone)
        report["previous_day"] = daily[previous] if previous in comparable else None
        report["baseline_days_available"] = len(comparable)
        report["baseline"] = [daily[item] for item in sorted(comparable)]
        report["baseline_summary"] = {"method": "MEDIAN", "expected_days": 7,
            "available_days": len(comparable), "status": "AVAILABLE" if len(comparable) == 7 else
                "PARTIAL_BASELINE" if comparable else "UNAVAILABLE_BASELINE",
            "missing_days": [item.isoformat() for item in baseline if item not in comparable]}
        previous_events = {item["event_name"]: item for item in daily[previous]["events"]} if previous in comparable else {}
        baseline_events = [{item["event_name"]: item for item in daily[value]["events"]} for value in sorted(comparable)]
        for event in report["events"]:
            name = event["event_name"]
            event["previous_day_comparison"] = _compare_metrics(event,
                [previous_events[name]] if name in previous_events else [], 1, "UNAVAILABLE_PREVIOUS_DAY")
            event["baseline_comparison"] = _compare_metrics(event,
                [items[name] for items in baseline_events], 7, "UNAVAILABLE_BASELINE")
        start, end = utc_window(day)
        report["window"] = {"start": start.isoformat(), "end_exclusive": end.isoformat()}
        report["table_coverage"] = coverage[(target_day - day).days]
        report["trend_collection_enabled"] = False
        reports.append(report)
        candidates.extend(build_candidates(day, rows, rules, now, rules_version, policy, contracts, exclusions))
    selected = select_proposals(candidates, policy)
    selected_keys = {item["candidate_key"]: index for index, item in enumerate(selected, 1)}
    selected_accounts = {item["account_id"]: item["candidate_key"] for item in selected}
    per_group = Counter(tuple(item["group"]) for item in selected)
    for candidate in candidates:
        key, account, group = candidate["candidate_key"], candidate["account_id"], tuple(candidate["group"])
        reason = ("SELECTED_PREVIEW" if key in selected_keys else
                  "MERGED_INTO_SELECTED_ACCOUNT" if account in selected_accounts else
                  "GROUP_LIMIT" if per_group[group] >= policy.maximum_per_group else "TOTAL_ACCOUNT_LIMIT")
        candidate["selection"] = {"reason": reason, "order": selected_keys.get(key),
                                  "selected_candidate_key": selected_accounts.get(account), "budget_scope": "CURRENT_RUN"}
    selections = {item["candidate_key"]: item["selection"] for item in candidates}
    for candidate in selected:
        candidate["selection"] = selections[candidate["candidate_key"]]
    rule_map = {rule.event_name: rule for rule in rules}
    observations = [row for row in rows if row.day in days and (row.event_name in rule_map or row.event_name == "app_previous_process_exit")]
    observed_accounts = {row.account_id for row in observations if row.account_id}
    eligible_accounts = {row.account_id for row in observations if _candidate_issue(
        row, rule_map.get(row.event_name), contracts, now, policy) is None}
    return {"target_day": target_day.isoformat(), "latest_available_day": latest.isoformat() if latest else None,
            "status": "DAILY_EXPORT_AVAILABLE" if target_day in available else "WAITING_EXPORT",
            "timezone": "UTC", "query_cutoff": now.isoformat(), "property_timezone": property_timezone,
            "analytics_user_metric": "DISTINCT_USER_PSEUDO_ID",
            "rules_version": rules_version, "available_tables": sorted(available_tables), "reports": reports,
            "day_coverage": coverage,
            "candidate_pool": candidates, "candidate_proposals": selected, "candidate_exclusions": exclusions,
            "candidate_summary": {"unit": "DISTINCT_ACCOUNT_ID", "statistical_days": [day.isoformat() for day in sorted(days)],
                "funnel": {"observed_accounts": len(observed_accounts), "eligible_accounts": len(eligible_accounts),
                           "matched_accounts": len({item["account_id"] for item in candidates}), "proposed_accounts": len(selected)},
                "exclusion_observations_by_reason": dict(sorted(Counter(item["reason"] for item in exclusions).items())),
                "selection_observations_by_reason": dict(sorted(Counter(item["selection"]["reason"] for item in candidates).items()))},
            "dispatch_enabled": False, "quota_authoritative": False,
            "integration_dependencies": ["BACKEND_TARGET_AUTHORIZATION", "BACKEND_ATOMIC_QUOTA_AND_TASK_ADMISSION"],
            "policy": vars(policy)}
