#!/usr/bin/env python3
"""Read-only management API. Analysis and import remain separate offline programs."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import psycopg

from api_models import AccountId, Context, ErrorReply, Meta, NoQuery, Page, PageQuery, Report, RunDetail, RunId, RunPage, UserPage
from db import SCOPE, connect

app = FastAPI(title="埋点分析管理只读 API", version="1.0.0", docs_url=None, redoc_url=None,
              openapi_url="/api/openapi.json")
router = APIRouter(prefix="/api/v1", responses={400:{"model":ErrorReply},403:{"model":ErrorReply},
                    404:{"model":ErrorReply},500:{"model":ErrorReply},503:{"model":ErrorReply}})
QueryPage = Annotated[PageQuery, Query()]
EmptyQuery = Annotated[NoQuery, Query()]


def error(status, code, message):
    return JSONResponse(status_code=status, content={"error":{"code":code,"message":message}},
                        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})


@app.middleware("http")
async def local_read_only_boundary(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0]
    if host not in {"127.0.0.1","localhost","api"} or request.headers.get("sec-fetch-site") == "cross-site":
        response = error(403,"LOCAL_ONLY","仅允许本机同站点访问。")
    elif request.method not in {"GET","HEAD"}:
        response = error(405,"READ_ONLY","当前管理 API 仅提供只读查询。")
    elif len(str(request.url)) > 2048 or len(request.query_params) != len(request.query_params.multi_items()):
        response = error(400,"INVALID_QUERY","查询参数重复或过长。")
    else:
        try:
            response = await call_next(request)
        except Exception:
            response = error(500,"INTERNAL_ERROR","查询暂时无法完成，请稍后重试。")
    response.headers.update({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff", "Referrer-Policy":"no-referrer"})
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, _exception):
    return error(400,"INVALID_QUERY","请使用合法账号 ID、批次 ID、ISO 日期和分页参数。")


@app.exception_handler(StarletteHTTPException)
async def http_error(_request, exception):
    return error(exception.status_code,"NOT_FOUND" if exception.status_code == 404 else "REQUEST_ERROR",
                 "记录不存在于当前 scope。" if exception.status_code == 404 else "请求无法处理。")


@app.exception_handler(psycopg.Error)
async def database_unavailable(_request, _exception):
    return error(503,"DATABASE_UNAVAILABLE","数据库暂时不可用，请稍后重试。")


def require_run(conn, run_id):
    if not conn.execute("SELECT 1 FROM analytics.telemetry_runs WHERE scope_key=%s AND run_id=%s",(SCOPE,run_id)).fetchone():
        raise HTTPException(404)


@app.get("/healthz", include_in_schema=False)
@app.get("/api/healthz", include_in_schema=False)
def health():
    with connect(read_only=True) as conn:
        conn.execute("SELECT 1")
    return {"status":"ok","read_only":True}


@router.get("/meta", response_model=Meta)
def meta(_query: EmptyQuery):
    return Meta(scope=SCOPE)


@router.get("/runs", response_model=RunPage)
def runs(query: QueryPage):
    predicate = """r.scope_key=%s AND (%s='' OR EXISTS(SELECT 1 FROM analytics.diagnostic_contexts c
        WHERE c.run_id=r.run_id AND c.account_id=%s))"""
    values = (SCOPE,query.account,query.account)
    with connect(read_only=True) as conn:
        total = conn.execute(f"SELECT count(*) AS n FROM analytics.telemetry_runs r WHERE {predicate}",values).fetchone()["n"]
        items = conn.execute(f"""SELECT r.run_id,r.target_day,r.data_status,r.process_status,r.created_at,
            (SELECT count(*) FROM analytics.daily_reports d WHERE d.run_id=r.run_id) AS reports,
            (SELECT count(*) FROM analytics.diagnostic_contexts c WHERE c.run_id=r.run_id) AS accounts,
            (SELECT count(*) FROM analytics.telemetry_findings f WHERE f.run_id=r.run_id) AS findings
            FROM analytics.telemetry_runs r WHERE {predicate} ORDER BY r.created_at DESC,r.run_id LIMIT %s OFFSET %s""",
            (*values,query.limit,query.offset)).fetchall()
    return {"items":items,"total":total,"limit":query.limit,"offset":query.offset}


@router.get("/runs/{run_id}", response_model=RunDetail)
def run_detail(run_id: RunId, _query: EmptyQuery):
    with connect(read_only=True) as conn:
        row = conn.execute("""SELECT run_id,target_day,data_status,process_status,snapshot_id,source_sha256,
            implementation_sha256,rules_version,provenance,archive_manifest,source_manifest,
            analysis->'candidate_summary' AS candidate_summary, analysis->'policy' AS policy,
            analysis->'day_coverage' AS day_coverage FROM analytics.telemetry_runs WHERE scope_key=%s AND run_id=%s""",
            (SCOPE,run_id)).fetchone()
        if row is None:
            raise HTTPException(404)
        row["report_days"] = [x["statistical_day"] for x in conn.execute(
            "SELECT statistical_day FROM analytics.daily_reports WHERE run_id=%s ORDER BY statistical_day DESC",(run_id,)).fetchall()]
        row["executions"] = conn.execute("SELECT execution_id,namespace,flow_id FROM analytics.run_executions WHERE run_id=%s ORDER BY execution_id",(run_id,)).fetchall()
    return row


@router.get("/runs/{run_id}/reports/{day}", response_model=Report)
def report(run_id: RunId, day: date, _query: EmptyQuery):
    with connect(read_only=True) as conn:
        row = conn.execute("""SELECT d.statistical_day,d.content FROM analytics.daily_reports d
            JOIN analytics.telemetry_runs r USING(run_id) WHERE r.scope_key=%s AND r.run_id=%s AND d.statistical_day=%s""",
            (SCOPE,run_id,day)).fetchone()
    if row is None:
        raise HTTPException(404)
    return row


USER_COLUMNS = """c.account_id,c.run_id,c.context_id,c.selection_order,c.selection_outcome,c.target_state,c.proposal,
    jsonb_array_length(c.content->'findings') AS findings,jsonb_array_length(c.content->'observations') AS facts,
    r.target_day,r.created_at AS imported_at"""


def list_users(run_id=None, account_id="", query=None):
    values = (SCOPE,run_id,run_id,account_id,account_id)
    predicate = "r.scope_key=%s AND (%s::text IS NULL OR c.run_id=%s) AND (%s='' OR c.account_id=%s)"
    with connect(read_only=True) as conn:
        if run_id:
            require_run(conn,run_id)
        total = conn.execute(f"SELECT count(*) AS n FROM analytics.diagnostic_contexts c JOIN analytics.telemetry_runs r USING(run_id) WHERE {predicate}",values).fetchone()["n"]
        items = conn.execute(f"""SELECT {USER_COLUMNS} FROM analytics.diagnostic_contexts c
            JOIN analytics.telemetry_runs r USING(run_id) WHERE {predicate}
            ORDER BY r.created_at DESC,r.run_id,c.selection_order LIMIT %s OFFSET %s""",(*values,query.limit,query.offset)).fetchall()
    return {"items":items,"total":total,"limit":query.limit,"offset":query.offset}


@router.get("/runs/{run_id}/users", response_model=UserPage)
def run_users(run_id: RunId, query: QueryPage):
    return list_users(run_id,query.account,query)


@router.get("/users/{account_id}", response_model=UserPage)
def user_history(account_id: AccountId, query: QueryPage):
    if query.account:
        raise HTTPException(400)
    return list_users(account_id=account_id,query=query)


@router.get("/users/{account_id}/contexts/{run_id}", response_model=Context)
def user_context(account_id: AccountId, run_id: RunId, _query: EmptyQuery):
    with connect(read_only=True) as conn:
        row = conn.execute("""SELECT c.account_id,c.run_id,c.context_id,c.selection_order,c.selection_outcome,c.target_state,c.proposal,c.content
            FROM analytics.diagnostic_contexts c JOIN analytics.telemetry_runs r USING(run_id)
            WHERE r.scope_key=%s AND c.account_id=%s AND c.run_id=%s""",(SCOPE,account_id,run_id)).fetchone()
    if row is None:
        raise HTTPException(404)
    return row


def archived_rows(run_id, field, query):
    # The two field names come only from registered routes, never from client SQL input.
    with connect(read_only=True) as conn:
        require_run(conn,run_id)
        values = (run_id,SCOPE,query.account,query.account)
        source = f"""FROM analytics.telemetry_runs r CROSS JOIN LATERAL
            jsonb_array_elements(r.analysis->'{field}') WITH ORDINALITY AS e(item,position)
            WHERE r.run_id=%s AND r.scope_key=%s AND (%s='' OR item->>'account_id'=%s)"""
        total = conn.execute(f"SELECT count(*) AS n {source}",values).fetchone()["n"]
        items = [x["item"] for x in conn.execute(f"SELECT item {source} ORDER BY position LIMIT %s OFFSET %s",
                                               (*values,query.limit,query.offset)).fetchall()]
    return {"items":items,"total":total,"limit":query.limit,"offset":query.offset}


@router.get("/runs/{run_id}/candidates", response_model=Page)
def candidates(run_id: RunId, query: QueryPage):
    return archived_rows(run_id,"candidate_pool",query)


@router.get("/runs/{run_id}/exclusions", response_model=Page)
def exclusions(run_id: RunId, query: QueryPage):
    return archived_rows(run_id,"candidate_exclusions",query)


app.include_router(router)
# Validation is deliberately 400, so the generated contract must match the handler.
for path in app.openapi()["paths"].values():
    for operation in path.values():
        if isinstance(operation, dict):
            operation.get("responses", {}).pop("422", None)
