#!/usr/bin/env python3
"""Build private, account-linked diagnostic evidence from a verified frozen snapshot."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from ga4_log_collection import write_private
from ga4_report.log_collection import _reason_issue, build_query, parse_rows
from ga4_report.rules import load_report_rules, schema_contract


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def verify_snapshot(source: Path, manifest: dict, rules: tuple) -> dict:
    payload = source.read_bytes()
    if manifest.get("status") != "READY" or hashlib.sha256(payload).hexdigest() != manifest["source_sha256"]:
        raise ValueError("Frozen snapshot is not ready or its checksum changed")
    data = json.loads(payload)
    query = build_query("looktech-online.analytics_506558519", date.fromisoformat(manifest["query_start"]),
        date.fromisoformat(manifest["query_end_exclusive"]) - timedelta(days=1), set(data["available_tables"]), rules)
    if hashlib.sha256(query.encode()).hexdigest() != manifest["query_sha256"]:
        raise ValueError("Frozen snapshot does not cover the current query scope")
    if len(data["rows"]) != manifest["row_count"] or sum(int(row["records"]) for row in data["rows"]) != manifest["event_record_count"]:
        raise ValueError("Frozen snapshot row or event count changed")
    return data


def investigation_hint(event: str, reason: str | None, platform: str) -> dict:
    area = {"device": "设备连接与控制链路", "media": "媒体导入与处理链路", "note": "笔记录音与处理链路",
        "app": "App 启动与进程", "account": "账号与鉴权", "translation": "翻译会话", "chat": "AI 对话"}.get(event.split("_")[0], "事件对应的业务链路")
    if reason in {"crash", "crash_native", "anr"}:
        checks = ["核对崩溃栈或 ANR 主线程、进程退出记录", "核对对应 App 构建与原生符号，排除正常退出"]
    elif reason in {"network_error", "timeout", "session_ready_timeout", "rtc_join_failed"}:
        checks = ["检查连接或请求的开始、超时、响应及重试", "对照网络切换、设备断连和服务端错误，区分超时发生位置"]
    elif reason == "unsupported_state":
        checks = ["检查失败前后的状态迁移、重入、取消与连接状态", "核对调用前置条件，区分正常拒绝与状态机异常"]
    else:
        checks = ["检查失败入口、SDK 返回或异常栈及前置状态", "对照同窗口成功事件；unknown 不代表已确认 SDK 根因"]
    return {"status": "HYPOTHESIS", "confidence": "UNVERIFIED", "generator": "RULE_HINTS_V1",
        "suspected_area": area, "primary_app_direction": platform, "checks": checks,
        "search_terms": list(dict.fromkeys([*event.split("_"), *([reason] if reason else [])])),
        "search_terms_are_exact_log_tags": False, "requires_supporting_and_refuting_log_evidence": True}


def build_contexts(data: dict, manifest: dict, result: dict) -> tuple[dict, dict]:
    version, rules = load_report_rules()
    contracts = schema_contract()[1]
    rule_map = {rule.event_name: rule for rule in rules}
    if result["dispatch_enabled"] or result["quota_authoritative"] or result["rules_version"] != version:
        raise ValueError("Expected an analysis preview using the current rules")
    if set(result["available_tables"]) != set(data["available_tables"]):
        raise ValueError("Analysis and snapshot table coverage differ")
    root = Path(__file__).resolve().parents[1]
    code = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [Path(__file__), root / "tools/ga4_log_collection.py", root / "tools/ga4_report/log_collection.py", root / "tools/ga4_report/rules.py", *sorted((root / "analytics_schema").glob("*.yaml"))]}
    provenance = {"snapshot_id": manifest["snapshot_id"], "source_sha256": manifest["source_sha256"],
        "analysis_sha256": digest(result), "implementation_sha256": digest(code), "rules_version": version,
        "captured_at": manifest["captured_at"], "query_start": manifest["query_start"],
        "query_end_exclusive": manifest["query_end_exclusive"], "evaluation_as_of": result["query_cutoff"],
        "target_day": result["target_day"], "scope": "ai.looktech.glasses.memo/prod/us/release"}
    run_id = digest(provenance)
    proposals = {item["account_id"]: item for item in result["candidate_proposals"]}
    if len(proposals) != len(result["candidate_proposals"]) or any(not re.fullmatch(r"[1-9][0-9]*", account) for account in proposals):
        raise ValueError("Selected accounts must be valid and deduplicated")
    observations: dict[str, list] = {account: [] for account in proposals}
    for raw in data["rows"]:
        account = str(raw.get("user_id") or "")
        if account not in observations:
            continue
        parsed = parse_rows([raw], rules)
        if not parsed:
            continue
        row = parsed[0]
        allowed = contracts.get(row.event_name, {})
        rule = rule_map.get(row.event_name)
        dimension = rule.reason_dimension.split(":")[-1] if rule else "exit_reason"
        if dimension == "error_source":
            dimension = "failure_reason"
        auxiliary_crash = row.event_name == "app_previous_process_exit" and row.reason in {"crash", "crash_native", "anr"}
        reason = row.reason if row.reason in allowed.get(dimension, ()) or auxiliary_crash else None
        first = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(raw["first_us"]))
        if first.date() != row.day or first > row.last_at:
            raise ValueError("Invalid aggregate time bounds")
        fact = {"event_name": row.event_name, "statistical_day": str(row.day), "platform": row.platform,
            "app_version": row.version if re.fullmatch(r"[A-Za-z0-9.+_-]{1,64}", row.version) else None,
            "records": row.records, "reason": reason,
            "error_source": row.error_source if row.error_source in allowed.get("error_source", ()) else None,
            "sync_state": row.sync_state if row.sync_state in allowed.get("sync_state", ()) else None,
            "first_event_at": first.isoformat(), "last_event_at": row.last_at.isoformat(),
            "parameter_status": "VALID" if row.routing_valid else "AMBIGUOUS_PARAMETERS",
            "reason_status": _reason_issue(row, rule, contracts) if rule or row.event_name == "app_previous_process_exit" else None}
        row_hash = digest(raw)
        observations[account].append({"fact_id": digest([manifest["source_sha256"], row_hash]), "source_row_sha256": row_hash, **fact})
    reports = {report["statistical_day"]: {event["event_name"]: event for event in report["events"]} for report in result["reports"]}
    contexts = {}
    account_index = {}
    for account, proposal in proposals.items():
        findings = []
        for candidate in result["candidate_pool"]:
            if candidate["account_id"] != account:
                continue
            event, reason = candidate["evidence"]["event_name"], candidate["evidence"]["failure_reason"]
            facts = [item["fact_id"] for item in observations[account] if item["event_name"] == event and
                item["statistical_day"] == candidate["statistical_day"] and item["platform"] == candidate["platform"] and
                item["reason"] == reason and item["parameter_status"] == "VALID" and
                (event != "device_usage_media_sync_failed" or item["error_source"] == candidate["evidence"]["error_source"])]
            linked_records = sum(item["records"] for item in observations[account] if item["fact_id"] in facts)
            if not facts or linked_records != candidate["records"]:
                raise ValueError("A candidate has no matching facts in the frozen snapshot")
            metric = reports[candidate["statistical_day"]].get(event)
            findings.append({"finding_id": candidate["candidate_key"], "event_name": event,
                "platform": candidate["platform"], "statistical_day": candidate["statistical_day"],
                "app_versions": candidate["app_versions"], "reason": reason, "matched_rules": candidate["matched_rules"],
                "account_records": candidate["records"], "group_accounts": candidate["group_accounts"],
                "selection": candidate["selection"], "evidence_fact_ids": facts,
                "population_comparison": {"scope": "ALL_FILTERED_ACCOUNTS_AND_PLATFORMS",
                    "previous_day": metric["previous_day_comparison"], "baseline": metric["baseline_comparison"]} if metric else None,
                "investigation": investigation_hint(event, reason, candidate["platform"])})
        context = {"schema_version": 1, "run_id": run_id, "account_id": account, "provenance": provenance,
            "evidence_granularity": "UTC_DAY_AGGREGATES", "event_timeline_available": False,
            "observations": observations[account], "findings": findings,
            "exclusions": [item for item in result["candidate_exclusions"] if item.get("account_id") == account],
            "limitations": ["只含固定查询范围，不是该账号全部埋点", "聚合内无事件顺序，不能构造精确前后时间线",
                "业务账号可跨手机与版本；没有证明是未来日志对应的同一手机", "候选与假设不是已确认根因，也不是已创建采集任务",
                "日志到达后需重新核验覆盖时间、平台、版本和时钟质量，允许无重叠或证据不足"]}
        context_id = digest(context)
        contexts[context_id] = context
        account_index[account] = context_id
    bundle = {"schema_version": 1, "run_id": run_id, "provenance": provenance,
        "account_index": account_index, "contexts": contexts, "dispatch_enabled": False}
    summary = {"run_id": run_id, "snapshot_id": manifest["snapshot_id"], "source_sha256": manifest["source_sha256"],
        "analysis_status": result["status"], "target_day": result["target_day"], "latest_available_day": result["latest_available_day"],
        "context_count": len(contexts), "hypothesis_count": sum(len(item["findings"]) for item in contexts.values()),
        "funnel": result["candidate_summary"]["funnel"], "dispatch_enabled": False, "notifications_sent": 0,
        "event_timeline_available": False}
    return bundle, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    _, rules = load_report_rules()
    manifest = json.loads(args.manifest.read_text())
    data = verify_snapshot(args.input, manifest, rules)
    if args.analysis:
        if not args.output or not args.summary:
            parser.error("--analysis requires --output and --summary")
        bundle, summary = build_contexts(data, manifest, json.loads(args.analysis.read_text()))
        write_private(args.output, bundle)
        write_private(args.summary, summary)
        print(json.dumps(summary))
    else:
        print(json.dumps({"snapshot_verified": True, "rows": manifest["row_count"]}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f"Diagnostic context failed: {type(error).__name__}") from None
