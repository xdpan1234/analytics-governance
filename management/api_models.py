"""Typed read-only API envelope; archived JSON keeps its original field names."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

RunId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
AccountId = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,63}$")]
JsonObject = dict[str, JsonValue]


class NoQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    account: str = Field(default="", pattern=r"^(?:[1-9][0-9]{0,63})?$")


class Page(BaseModel):
    items: list[JsonObject]
    total: int
    limit: int
    offset: int


class RunSummary(BaseModel):
    run_id: RunId
    target_day: date
    data_status: str
    process_status: Literal["SUCCEEDED"]
    created_at: datetime
    reports: int
    accounts: int
    findings: int


class RunPage(BaseModel):
    items: list[RunSummary]
    total: int
    limit: int
    offset: int


class ExecutionRef(BaseModel):
    execution_id: str
    namespace: str
    flow_id: str


class RunDetail(BaseModel):
    run_id: RunId
    target_day: date
    data_status: str
    process_status: str
    snapshot_id: str
    source_sha256: str
    implementation_sha256: str
    rules_version: str
    provenance: JsonObject
    archive_manifest: JsonObject
    source_manifest: JsonObject
    candidate_summary: JsonObject
    policy: JsonObject
    day_coverage: list[JsonObject]
    report_days: list[date]
    executions: list[ExecutionRef]


class Report(BaseModel):
    statistical_day: date
    content: JsonObject


class UserSummary(BaseModel):
    account_id: AccountId
    run_id: RunId
    context_id: str
    selection_order: int
    selection_outcome: str
    target_state: str
    proposal: JsonObject
    findings: int
    facts: int
    target_day: date
    imported_at: datetime


class UserPage(BaseModel):
    items: list[UserSummary]
    total: int
    limit: int
    offset: int


class Context(BaseModel):
    account_id: AccountId
    run_id: RunId
    context_id: str
    selection_order: int
    selection_outcome: str
    target_state: str
    proposal: JsonObject
    content: JsonObject


class Meta(BaseModel):
    scope: str
    read_only: Literal[True] = True
    mode: Literal["FROZEN_REPLAY"] = "FROZEN_REPLAY"
    dispatch_enabled: Literal[False] = False
    notifications_sent: Literal[0] = 0


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorReply(BaseModel):
    error: ErrorBody
