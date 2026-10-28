#!/usr/bin/env python3
"""Read GA4 daily exports as UTC days and write private App-log collection proposals."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ga4_report.log_collection import CollectionPolicy, build_collection_result, build_query, required_tables
from ga4_report.rules import load_report_rules, validate_rules


def bq(arguments: list[str]) -> Any:
    executable = shutil.which("bq")
    if not executable:
        raise RuntimeError("The bq CLI is required for live reads; use --input for an exported fixture")
    result = subprocess.run([executable, "--format=json", *arguments], capture_output=True, text=True, check=False)
    if result.returncode:
        # CLI output may contain queries or identifiers. Do not copy it into public runtime logs.
        raise RuntimeError("BigQuery read failed; inspect the authenticated bq session")
    return json.loads(result.stdout)


def write_private(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="JSON containing rows and available_tables; no live query")
    parser.add_argument("--dataset", default="looktech-online.analytics_506558519")
    parser.add_argument("--property-timezone", default="Asia/Shanghai")
    parser.add_argument("--day", type=date.fromisoformat, help="Target UTC day; default previous UTC day")
    parser.add_argument("--as-of", help="Timezone-aware ISO timestamp; default current UTC time")
    parser.add_argument("--output", type=Path, required=True, help="Private local result JSON; never dispatches tasks")
    parser.add_argument("--maximum-bytes-billed", type=int, default=1024 * 1024 * 1024)
    parser.add_argument("--policy", type=Path, help="Optional JSON CollectionPolicy overrides")
    parser.add_argument("--render-sql", action="store_true", help="Write SQL only using supplied table metadata")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else datetime.now(UTC)
    if now.tzinfo is None:
        parser.error("--as-of must include a timezone")
    day = args.day or now.astimezone(UTC).date() - timedelta(days=1)
    version, rules = load_report_rules()
    validate_rules(rules)
    policy = CollectionPolicy(**json.loads(args.policy.read_text())) if args.policy else CollectionPolicy()
    if args.maximum_bytes_billed <= 0:
        parser.error("--maximum-bytes-billed must be positive")
    if args.input:
        source = json.loads(args.input.read_text(encoding="utf-8"))
        tables = set(source["available_tables"])
    else:
        metadata = bq(["ls", "--max_results=100000", args.dataset.replace(".", ":", 1)])
        tables = {item["tableReference"]["tableId"] for item in metadata}
        source = {"rows": []}
    # Fourteen UTC days cover the oldest fallback day plus its seven-day baseline.
    wanted_tables = set().union(*(required_tables(day - timedelta(days=i), args.property_timezone) for i in range(14)))
    has_daily_tables = bool(wanted_tables & tables)
    query = build_query(args.dataset, day - timedelta(days=13), day, tables, rules, args.property_timezone) if has_daily_tables else None
    if args.render_sql:
        write_private(args.output, {"sql": query, "status": "SQL_READY" if query else "WAITING_EXPORT", "dispatch_enabled": False})
    else:
        if not args.input and query:
            source["rows"] = bq(["query", "--use_legacy_sql=false", "--max_rows=1000000",
                                  f"--maximum_bytes_billed={args.maximum_bytes_billed}", query])
            if len(source["rows"]) >= 1000000:
                raise RuntimeError("BigQuery output may be truncated; refusing to publish partial facts")
        result = build_collection_result(source["rows"], tables, day, now, rules, version, args.property_timezone, policy)
        write_private(args.output, result)
    print(json.dumps({"output": str(args.output), "dispatch_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, RuntimeError, OSError) as error:
        print(f"Collection analysis failed: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
