from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RuleError(ValueError):
    pass


@dataclass(frozen=True)
class OutcomeRule:
    event_name: str
    outcome_type: str
    denominator_event: str | None
    reason_dimension: str


def _scalar(value: str) -> str | None:
    value = value.strip().strip('"\'')
    return None if value in {"null", "~", ""} else value


def load_report_rules(path: Path | None = None) -> tuple[str, tuple[OutcomeRule, ...]]:
    path = path or Path(__file__).resolve().parents[2] / "analytics_schema" / "report_rules.yaml"
    version: str | None = None
    records: list[dict[str, str | None]] = []
    current: dict[str, str | None] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("rules_version:"):
            version = _scalar(stripped.split(":", 1)[1])
        elif stripped == "- event_name:" or stripped.startswith("- event_name:"):
            if current:
                records.append(current)
            current = {"event_name": _scalar(stripped.split(":", 1)[1])}
        elif current is not None and re.match(r"^[a-z_]+:", stripped):
            key, value = stripped.split(":", 1)
            current[key] = _scalar(value)
    if current:
        records.append(current)
    if not version or not records:
        raise RuleError("report rules are invalid")
    try:
        rules = tuple(
            OutcomeRule(
                event_name=str(record["event_name"]),
                outcome_type=str(record["outcome_type"]),
                denominator_event=record.get("denominator_event"),
                reason_dimension=str(record["reason_dimension"]),
            )
            for record in records
        )
    except (KeyError, TypeError) as error:
        raise RuleError("report rules are invalid") from error
    if any(not rule.event_name or not rule.reason_dimension for rule in rules):
        raise RuleError("report rules are invalid")
    return version, rules


def schema_contract() -> tuple[set[str], dict[str, dict[str, frozenset[str]]]]:
    schema_dir = Path(__file__).resolve().parents[2] / "analytics_schema"
    event_pattern = re.compile(r"^\s*- event_name:\s*([a-z0-9_]+)\s*$")
    schema_events: set[str] = set()
    allowed_values: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for path in schema_dir.glob("*.yaml"):
        if path.name == "report_rules.yaml":
            continue
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
            if current_event and indent > current_event_indent and stripped == "allowed_values:":
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
                    allowed_values[current_event][current_param].add(value.strip().strip("'\""))
            elif stripped.endswith(":") and not stripped.startswith("- "):
                current_param = stripped[:-1]
            elif current_param and stripped.startswith("- "):
                allowed_values[current_event][current_param].add(stripped[2:].strip().strip("'\""))
    return schema_events, {
        event: {param: frozenset(values) for param, values in params.items()}
        for event, params in allowed_values.items()
    }


def validate_rules(rules: tuple[OutcomeRule, ...]) -> None:
    schema_events, allowed_values = schema_contract()
    mapped = {rule.event_name for rule in rules}
    denominators = {rule.denominator_event for rule in rules if rule.denominator_event}
    unknown = sorted((mapped | denominators) - schema_events)
    if len(mapped) != len(rules):
        raise RuleError("abnormal outcome mapping contains duplicate events")
    if unknown:
        raise RuleError("abnormal outcome mapping does not match the analytics schema")
    missing = [
        rule.event_name
        for rule in rules
        if not allowed_values.get(rule.event_name, {}).get(
            rule.reason_dimension.removeprefix("customEvent:")
        )
    ]
    if missing:
        raise RuleError("abnormal outcome reason mapping does not match the schema")


RULES_VERSION, OUTCOME_RULES = load_report_rules()
validate_rules(OUTCOME_RULES)
