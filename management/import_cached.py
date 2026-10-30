#!/usr/bin/env python3
"""Validate and atomically archive frozen analysis. No cloud or task/notification client."""
import argparse
from datetime import datetime, timedelta, UTC
import hashlib
import json
from pathlib import Path
import re

from psycopg.types.json import Jsonb
from db import SCOPE, connect


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    payload = path.read_bytes()
    require(len(payload) <= 100 * 1024 * 1024, "Archive exceeds local import limit")
    return json.loads(payload), hashlib.sha256(payload).hexdigest()


def validate(archive, snapshot):
    analysis, analysis_bytes = load(archive / "analysis.private.json")
    bundle, context_bytes = load(archive / "diagnostic-contexts.private.json")
    manifest, _ = load(snapshot / "manifest.json")
    source, source_hash = load(snapshot / "source.private.json")
    provenance = bundle["provenance"]
    require(manifest["status"] == "READY" and source_hash == manifest["source_sha256"] == provenance["source_sha256"],
            "Snapshot source checksum mismatch")
    require(len(source["rows"]) == manifest["row_count"] and
            sum(int(row["records"]) for row in source["rows"]) == manifest["event_record_count"], "Snapshot count mismatch")
    require(manifest["snapshot_id"] == provenance["snapshot_id"], "Snapshot identity mismatch")
    require(all(manifest[key] == provenance[key] for key in ["captured_at", "query_start", "query_end_exclusive"]),
            "Snapshot time bounds mismatch")
    require(provenance["scope"] == SCOPE and digest(provenance) == bundle["run_id"], "Scope or run identity mismatch")
    require(digest(analysis) == provenance["analysis_sha256"], "Analysis content checksum mismatch")
    require(analysis["dispatch_enabled"] is False and analysis["quota_authoritative"] is False and
            bundle["dispatch_enabled"] is False, "Only non-authoritative previews can be imported")
    require(analysis["rules_version"] == provenance["rules_version"] and
            analysis["target_day"] == provenance["target_day"] and analysis["query_cutoff"] == provenance["evaluation_as_of"],
            "Analysis evaluation metadata mismatch")
    require(set(source["available_tables"]) == set(analysis["available_tables"]), "Table coverage mismatch")
    proposals = {row["account_id"]: row for row in analysis["candidate_proposals"]}
    require(len(proposals) == len(analysis["candidate_proposals"]) and set(proposals) == set(bundle["account_index"]),
            "Selected account set mismatch")
    require(set(bundle["account_index"].values()) == set(bundle["contexts"]) and
            len(bundle["contexts"]) == len(proposals), "Context set mismatch")
    require(len({r["statistical_day"] for r in analysis["reports"]}) == len(analysis["reports"]), "Duplicate report day")
    source_rows = {digest(row): row for row in source["rows"]}
    pool = {row["candidate_key"]: row for row in analysis["candidate_pool"]}
    for account, context_id in bundle["account_index"].items():
        require(re.fullmatch(r"[1-9][0-9]*", account), "Invalid selected account")
        context = bundle["contexts"][context_id]
        require(digest(context) == context_id and context["account_id"] == account and
                context["run_id"] == bundle["run_id"] and context["provenance"] == provenance, "Context ownership or checksum mismatch")
        require(context["evidence_granularity"] == "UTC_DAY_AGGREGATES" and context["event_timeline_available"] is False,
                "Unsupported evidence granularity")
        require(proposals[account]["selection"]["reason"] == "SELECTED_PREVIEW", "Unexpected selection outcome")
        facts = {row["fact_id"]: row for row in context["observations"]}
        require(len(facts) == len(context["observations"]), "Duplicate fact reference")
        for fact in facts.values():
            raw = source_rows.get(fact["source_row_sha256"])
            require(raw is not None and str(raw["user_id"]) == account and fact["fact_id"] ==
                    digest([source_hash, fact["source_row_sha256"]]), "Fact source or account isolation mismatch")
            require(fact["event_name"] == raw["event_name"] and fact["records"] == int(raw["records"]) and
                    fact["statistical_day"] == raw["utc_day"] and fact["platform"] == raw["platform"], "Fact values mismatch")
            epoch = datetime(1970,1,1,tzinfo=UTC)
            require(datetime.fromisoformat(fact["first_event_at"]) == epoch + timedelta(microseconds=int(raw["first_us"])) and
                    datetime.fromisoformat(fact["last_event_at"]) == epoch + timedelta(microseconds=int(raw["last_us"])),
                    "Fact time bounds mismatch")
        require({f["finding_id"] for f in context["findings"]} ==
                {c["candidate_key"] for c in pool.values() if c["account_id"] == account}, "Selected finding set mismatch")
        for finding in context["findings"]:
            candidate = pool[finding["finding_id"]]
            require(finding["selection"] == candidate["selection"] and finding["matched_rules"] == candidate["matched_rules"] and
                    finding["account_records"] == candidate["records"], "Finding selection or counts mismatch")
            refs = finding["evidence_fact_ids"]
            require(refs and len(set(refs)) == len(refs) and set(refs) <= set(facts) and
                    sum(facts[ref]["records"] for ref in refs) == finding["account_records"], "Finding evidence mismatch")
        require(context["exclusions"] == [x for x in analysis["candidate_exclusions"] if x.get("account_id") == account],
                "Account exclusion mismatch")
    archive_manifest = {"analysis_file_sha256": analysis_bytes, "contexts_file_sha256": context_bytes,
                        "contexts_content_sha256": digest(bundle), "import_contract_version": 1}
    return analysis, bundle, manifest, archive_manifest


def persist(analysis, bundle, manifest, archive_manifest, execution_id=None):
    provenance, run_id = bundle["provenance"], bundle["run_id"]
    ingest_hash = digest([analysis, bundle, manifest, archive_manifest])
    with connect() as conn:
        # Serialize only the same immutable batch; all children commit in this transaction.
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (int(run_id[:15], 16),))
        existing = conn.execute("SELECT ingest_sha256 FROM analytics.telemetry_runs WHERE run_id=%s", (run_id,)).fetchone()
        if existing:
            require(existing["ingest_sha256"] == ingest_hash, "Existing run has different immutable content")
        else:
            conn.execute("""INSERT INTO analytics.telemetry_runs
                (run_id,scope_key,mode,target_day,evaluation_as_of,snapshot_id,source_sha256,rules_version,
                 implementation_sha256,data_status,process_status,ingest_sha256,analysis,provenance,archive_manifest,source_manifest)
                VALUES (%s,%s,'FROZEN_REPLAY',%s,%s,%s,%s,%s,%s,%s,'SUCCEEDED',%s,%s,%s,%s,%s)""",
                (run_id,SCOPE,analysis["target_day"],analysis["query_cutoff"],provenance["snapshot_id"],provenance["source_sha256"],
                 provenance["rules_version"],provenance["implementation_sha256"],analysis["status"],ingest_hash,
                 Jsonb(analysis),Jsonb(provenance),Jsonb(archive_manifest),Jsonb(manifest)))
            for report in analysis["reports"]:
                conn.execute("INSERT INTO analytics.daily_reports(report_revision_id,run_id,statistical_day,content_sha256,content) VALUES (%s,%s,%s,%s,%s)",
                    (digest([run_id,report["statistical_day"]]),run_id,report["statistical_day"],digest(report),Jsonb(report)))
            proposals = {row["account_id"]: row for row in analysis["candidate_proposals"]}
            for account, context_id in bundle["account_index"].items():
                context, proposal = bundle["contexts"][context_id], proposals[account]
                conn.execute("""INSERT INTO analytics.diagnostic_contexts
                    (context_id,run_id,account_id,target_state,selection_outcome,selection_order,proposal,content)
                    VALUES (%s,%s,%s,'UNRESOLVED','SELECTED_PREVIEW',%s,%s,%s)""",
                    (context_id,run_id,account,proposal["selection"]["order"],Jsonb(proposal),Jsonb(context)))
                for finding in context["findings"]:
                    conn.execute("""INSERT INTO analytics.telemetry_findings
                        (finding_revision_id,finding_key,run_id,account_id,context_id,statistical_day,platform,event_name,records,selection_reason,content)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (digest([run_id,finding["finding_id"]]),finding["finding_id"],run_id,account,context_id,
                         finding["statistical_day"],finding["platform"],finding["event_name"],finding["account_records"],
                         finding["selection"]["reason"],Jsonb(finding)))
        if execution_id:
            require(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", execution_id), "Invalid execution reference")
            conn.execute("INSERT INTO analytics.run_executions(run_id,execution_id,namespace,flow_id) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                         (run_id,execution_id,"local.analytics","bigquery-daily-analysis"))
        counts = {name:conn.execute(f"SELECT count(*) AS n FROM analytics.{name} WHERE run_id=%s", (run_id,)).fetchone()["n"]
                  for name in ["daily_reports","diagnostic_contexts","telemetry_findings"]}
        require(counts == {"daily_reports":len(analysis["reports"]),"diagnostic_contexts":len(bundle["contexts"]),
                          "telemetry_findings":sum(len(c["findings"]) for c in bundle["contexts"].values())}, "Incomplete stored batch")
    return {"run_id":run_id,"reused":bool(existing),**counts,"dispatch_enabled":False,"notifications_sent":0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",type=Path,required=True)
    parser.add_argument("--snapshot",type=Path,required=True)
    parser.add_argument("--execution-id")
    args = parser.parse_args()
    result = persist(*validate(args.archive,args.snapshot),execution_id=args.execution_id)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
