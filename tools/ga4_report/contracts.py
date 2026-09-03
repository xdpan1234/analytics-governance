from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


class ReportError(Exception):
    """A sanitized, user-facing report failure."""


@dataclass(frozen=True)
class DateRange:
    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ValueError("date range start_date must not be after end_date")

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def as_dict(self) -> dict[str, str]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
        }


@dataclass(frozen=True)
class ReportRequest:
    report_range: DateRange
    comparison_range: DateRange | None
    report_timezone: str
    environment: str | None = None


def metric(
    value: int | float | None,
    *,
    status: str = "available",
    numerator: int | float | None = None,
    denominator: int | float | None = None,
    previous: int | float | None = None,
    delta: int | float | None = None,
) -> dict[str, Any]:
    return {
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "status": status,
        "previous": previous,
        "delta": delta,
    }
