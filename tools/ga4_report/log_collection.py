"""UTC daily-export facts and bounded collection proposals; no task creation or push IO."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
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
        if not {"app_id", "stream_id", "environment", "build_region", "build_type", "user_pseudo_id"} <= raw.keys():
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
        if not re.fullmatch(r"[1-9][0-9]*", account) or int(account) > 2**63 - 1:
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
                                  raw.get("user_pseudo_id")))
    return rows


def _reason_allowed(row: CollectionRow, rule: OutcomeRule | None,
                    contracts: dict[str, dict[str, frozenset[str]]]) -> bool:
    if row.event_name == "app_previous_process_exit":
        return row.reason in {"crash", "anr"}
    if rule is None or row.reason is None:
        return False
    dimension = rule.reason_dimension.split(":")[-1]
    if dimension == "error_source":
        contract = contracts.get(row.event_name, {})
        return (row.error_source in contract.get("error_source", frozenset()) and
                row.reason in contract.get("failure_reason", frozenset()) and
                row.sync_state in contract.get("sync_state", frozenset()))
    return row.reason in contracts.get(row.event_name, {}).get(dimension, frozenset())


def _entry_rules(row: CollectionRow, rule: OutcomeRule | None, top10: set[str], group_accounts: int,
                 group_records: int, policy: CollectionPolicy) -> list[str]:
    if row.reason in EXPECTED_REASONS or not row.routing_valid:
        return []
    entries = []
    critical = row.event_name == "app_previous_process_exit" or row.event_name == "note_processing_failed" or row.reason in {"decode_error", "file_missing"}
    if critical and row.records >= policy.key_records:
        entries.append("KEY_SIGNAL")
    if row.reason in SDK_REASONS and row.records >= policy.sdk_records:
        entries.append("SDK_OR_UNKNOWN")
    if row.reason in NETWORK_REASONS and row.records >= policy.network_records:
        entries.append("NETWORK_OR_TIMEOUT")
    unexpected_outcome = rule is not None and rule.outcome_type != "blocked"
    if unexpected_outcome and row.event_name in top10 and group_accounts >= policy.impact_accounts:
        entries.append("TOP10_IMPACT")
    if unexpected_outcome and row.records >= policy.noisy_account_records and row.records * 2 >= group_records:
        entries.append("SINGLE_ACCOUNT_NOISE")
    return entries


def build_daily_report(day: date, rows: list[CollectionRow], rules: tuple[OutcomeRule, ...]) -> dict[str, Any]:
    selected = [row for row in rows if row.day == day]
    counts = Counter()
    accounts: dict[str, set[str]] = defaultdict(set)
    analytics_users: dict[str, set[str]] = defaultdict(set)
    unidentified_analytics_users: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    failures: dict[str, Counter[str]] = defaultdict(Counter)
    breakdowns: dict[str, Counter[tuple[str, str]]] = {"platform": Counter(), "version": Counter()}
    rule_map = {rule.event_name: rule for rule in rules}
    for row in selected:
        if not row.routing_valid:
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
        reason = row.error_source if rule and rule.reason_dimension == "customEvent:error_source" else row.reason
        reasons[row.event_name][reason or "MISSING_PARAMETER"] += row.records
        failures[row.event_name][row.reason or "MISSING_PARAMETER"] += row.records
    metrics = []
    for rule in rules:
        numerator = counts[rule.event_name]
        denominator = counts[rule.denominator_event] if rule.denominator_event else 0
        total = denominator + numerator if rule.outcome_type in {"failed", "degraded"} else denominator
        rate = numerator / total if rule.denominator_event and total > 0 else None
        metrics.append({"event_name": rule.event_name, "records": numerator, "identified_accounts": len(accounts[rule.event_name]),
                        "analytics_users": len(analytics_users[rule.event_name]),
                        "unidentified_analytics_user_records": unidentified_analytics_users[rule.event_name],
                        "outcome_type": rule.outcome_type, "denominator_event": rule.denominator_event,
                        "denominator_records": denominator, "result_rate": rate,
                        "failure_reasons": [{"reason": reason, "records": count} for reason, count in failures[rule.event_name].most_common(3)],
                        "top_reasons": [{"reason": reason, "records": count} for reason, count in reasons[rule.event_name].most_common(3)]})
        for dimension, values in breakdowns.items():
            details = []
            for value in sorted({value for (name, value) in values if name == rule.event_name}):
                records = values[rule.event_name, value]
                completed = values[rule.denominator_event, value] if rule.denominator_event else 0
                total = completed if rule.outcome_type == "blocked" else completed + records
                details.append({dimension: value, "records": records, "denominator_records": completed,
                                "result_rate": records / total if rule.denominator_event and total > 0 else None})
            metrics[-1][dimension + "_breakdown"] = details
    metrics.sort(key=lambda item: (-item["records"], item["event_name"]))
    return {"statistical_day": day.isoformat(), "timezone": "UTC", "top10": metrics[:10], "events": metrics,
            "diagnostic_signals": counts["app_previous_process_exit"],
            "ambiguous_routing_records": sum(row.records for row in selected if not row.routing_valid)}


def build_candidates(day: date, rows: list[CollectionRow], rules: tuple[OutcomeRule, ...], now: datetime,
                     rules_version: str, policy: CollectionPolicy | None = None,
                     contracts: dict[str, dict[str, frozenset[str]]] | None = None) -> list[dict[str, Any]]:
    if now.tzinfo is None:
        raise ValueError("The selection clock must include a timezone")
    policy = policy or CollectionPolicy()
    contracts = contracts if contracts is not None else schema_contract()[1]
    rule_map = {rule.event_name: rule for rule in rules}
    report = build_daily_report(day, rows, rules)
    top10 = {item["event_name"] for item in report["top10"] if item["records"] > 0}
    groups: dict[tuple[str, ...], list[CollectionRow]] = defaultdict(list)
    for row in rows:
        if row.day == day and row.routing_valid and row.platform in {"android", "ios"} and _reason_allowed(row, rule_map.get(row.event_name), contracts):
            groups[row.group].append(row)
    proposed = []
    for group, members in groups.items():
        population = {row.account_id for row in members if row.account_id}
        group_count = sum(row.records for row in members)
        per_account: dict[str, list[CollectionRow]] = defaultdict(list)
        for row in members:
            if row.account_id:
                per_account[row.account_id].append(row)
        for account, account_rows in per_account.items():
            last = max(row.last_at for row in account_rows)
            if not timedelta(0) <= now.astimezone(UTC) - last <= timedelta(hours=policy.maximum_age_hours):
                continue
            exemplar = account_rows[0]
            aggregate = CollectionRow(day, exemplar.event_name, exemplar.platform, exemplar.version, account,
                                      exemplar.reason, sum(row.records for row in account_rows), last, True,
                                      exemplar.error_source, exemplar.sync_state)
            entries = _entry_rules(aggregate, rule_map.get(aggregate.event_name), top10, len(population), group_count, policy)
            if not entries:
                continue
            key = json.dumps(["prod", "us", account, aggregate.platform, day.isoformat(), list(group)], separators=(",", ":"))
            proposed.append({"candidate_key": hashlib.sha256(key.encode()).hexdigest(), "account_id": account,
                             "platform": aggregate.platform, "statistical_day": day.isoformat(), "group": list(group),
                             "environment": "prod", "region": "us", "sources": ["APP"], "rule_version": rules_version,
                             "matched_rules": entries, "records": aggregate.records, "group_accounts": len(population),
                             "evidence": {"event_name": aggregate.event_name, "failure_reason": aggregate.reason,
                                          "error_source": aggregate.error_source,
                                          "sync_states": sorted({row.sync_state for row in account_rows if row.sync_state})},
                             "last_event_at": last.isoformat(), "app_versions": sorted({row.version for row in account_rows}),
                             "priority": 0 if "KEY_SIGNAL" in entries else 1, "disposition": "PROPOSED"})
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


def build_collection_result(raw_rows: list[dict[str, Any]], available_tables: set[str], target_day: date,
                            now: datetime, rules: tuple[OutcomeRule, ...], rules_version: str,
                            property_timezone: str = "Asia/Shanghai", policy: CollectionPolicy | None = None) -> dict[str, Any]:
    policy = policy or CollectionPolicy()
    rows = parse_rows(raw_rows, rules)
    recent = [target_day - timedelta(days=i) for i in range(7)]
    available = ready_days(recent, available_tables, property_timezone)
    latest = max(available) if available else None
    days = {day for day in recent[:4] if day in available}
    if latest:
        days.add(latest)
    reports = []
    candidates = []
    for day in sorted(days, reverse=True):
        report = build_daily_report(day, rows, rules)
        previous = day - timedelta(days=1)
        baseline = [day - timedelta(days=i) for i in range(1, 8)]
        comparable = ready_days(baseline, available_tables, property_timezone)
        report["previous_day"] = build_daily_report(previous, rows, rules) if previous in comparable else None
        report["baseline_days_available"] = len(comparable)
        report["baseline"] = [build_daily_report(item, rows, rules) for item in sorted(comparable)]
        report["trend_collection_enabled"] = False
        reports.append(report)
        candidates.extend(build_candidates(day, rows, rules, now, rules_version, policy))
    return {"target_day": target_day.isoformat(), "latest_available_day": latest.isoformat() if latest else None,
            "status": "DAILY_EXPORT_AVAILABLE" if target_day in available else "WAITING_EXPORT",
            "timezone": "UTC", "query_cutoff": now.isoformat(), "property_timezone": property_timezone,
            "analytics_user_metric": "DISTINCT_USER_PSEUDO_ID",
            "rules_version": rules_version, "available_tables": sorted(available_tables), "reports": reports,
            "candidate_pool": candidates, "candidate_proposals": select_proposals(candidates, policy),
            "dispatch_enabled": False, "quota_authoritative": False,
            "integration_dependencies": ["BACKEND_TARGET_AUTHORIZATION", "BACKEND_ATOMIC_QUOTA_AND_TASK_ADMISSION"],
            "policy": vars(policy)}
