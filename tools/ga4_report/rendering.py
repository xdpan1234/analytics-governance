from __future__ import annotations

import base64
import hashlib
import hmac
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from typing import Any

from .contracts import ReportError, ReportRequest


def _fmt(value: int | float | None) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.1f}"
    return f"{value:,}"


def _count_change(metric: dict[str, Any]) -> str:
    if metric["status"] == "new":
        return "new"
    if metric["delta"] is None:
        return "unavailable"
    if metric["delta"] == 0:
        return "0.0%"
    return f"{metric['delta'] * 100:+.1f}%"


def _rate_text(rate: dict[str, Any], label: str, comparison_label: str | None) -> str:
    if rate["status"] == "unavailable_zero_denominator":
        return f"{label} unavailable（分母为 0）"
    if rate["status"] != "available" or rate["value"] is None:
        return f"{label} unavailable"
    text = f"{label} {rate['value'] * 100:.1f}%（{rate['numerator']}/{rate['denominator']}）"
    if comparison_label and rate["previous"] is not None:
        return f"{text}，{comparison_label} {rate['delta'] * 100:+.1f} pp"
    return f"{text}，{comparison_label} unavailable" if comparison_label else text


class JsonRenderer:
    def render(self, report: dict[str, Any]) -> dict[str, Any]:
        return report


class FeishuRenderer:
    def render(self, report: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
        period = report["period"]
        comparison = report.get("comparison_period")
        summary = report["summary"]
        days = _days(period)
        title_type = "日报" if days == 1 else ("周报" if days == 7 else "报告")
        comparison_label = {"日报": "较前日", "周报": "较上周"}.get(title_type, "较上期") if comparison else None
        previous_label = {"日报": "前日", "周报": "上周"}.get(title_type, "上期")
        daily = title_type == "日报"
        events = report["events"][:10]
        overall_lines = ["**📊 昨日概览**" if daily else "**总体**"]
        if comparison:
            overall_lines.extend([
                f"异常事件：{_fmt(summary['abnormal_event_count']['value'])}（{previous_label} {_fmt(summary['abnormal_event_count']['previous'])}，{_count_change(summary['abnormal_event_count'])}）",
                f"影响用户：{_fmt(summary['affected_users']['value'])}（{previous_label} {_fmt(summary['affected_users']['previous'])}）",
            ])
        else:
            overall_lines.extend([
                f"异常事件：{_fmt(summary['abnormal_event_count']['value'])}",
                f"影响用户：{_fmt(summary['affected_users']['value'])}",
            ])
        overall_lines.append(f"活跃用户：{_fmt(summary['active_users']['value'])}")
        if comparison:
            overall_lines.append(f"对比周期：{comparison['start_date']}～{comparison['end_date']}")
        event_lines = ["**🚨 异常事件 Top 10**" if daily else "**异常事件 Top 10**"]
        if not events:
            event_lines.append({"日报": "昨日未检测到白名单业务异常事件", "周报": "本周未检测到白名单业务异常事件"}.get(title_type, "本期未检测到白名单业务异常事件"))
        for index, item in enumerate(events, start=1):
            line = f"{index}. `{item['event_name']}` — {_fmt(item['event_count']['value'])} 次，{_fmt(item['affected_users']['value'])} 用户"
            if comparison:
                line += f"；次数环比 {_count_change(item['event_count'])}"
            if item["rate"]:
                label = {"failed": "失败率", "blocked": "阻断率", "degraded": "降级率"}.get(item["outcome_type"], "结果率")
                line += "；" + _rate_text(item["rate"], label, comparison_label)
            elif item["per_1000_active_users"]:
                per = item["per_1000_active_users"]
                line += f"；每千活跃用户 {_fmt(per['value'])} 次" if per["value"] is not None else "；每千活跃用户 unavailable（活跃用户为 0）"
            event_lines.append(line)
        reason_lines = ["**🧭 主要原因**" if daily else "**主要原因**"]
        for index, item in enumerate(events, start=1):
            if index > 1:
                reason_lines.append("")
            reason_lines.append(f"**{index}｜{item['event_name']}**")
            reasons = item["reasons"]
            if reasons["status"] != "available":
                reason_lines.append("> 原因维度未注册，暂不可拆解")
                continue
            coverage = reasons["coverage"]
            reason_lines.append(
                f"> 原因覆盖率：{coverage['value'] * 100:.1f}%"
                f"（{_fmt(coverage['numerator'])}/{_fmt(coverage['denominator'])}）"
            )
            for reason in reasons["items"][:3]:
                share = reason["event_count"] / item["event_count"]["value"] * 100
                reason_lines.append(
                    f"> • `{reason['reason']}`：**{_fmt(reason['event_count'])} 次（{share:.1f}%）**；"
                    f"高发 {reason['platform']} / {reason['app_version']}：{_fmt(reason['context_count'])} 次"
                )
        if not events:
            reason_lines.append("本期无异常原因需要拆解")
        quality_lines = ["**🩺 数据质量**" if daily else "**数据质量**"]
        missing = report["quality"]["missing_dimensions"]
        quality_lines.append("未注册原因维度：" + "、".join(missing) if missing else "自定义原因维度均可查询")
        quality_lines.extend(dict.fromkeys(report["quality"]["warnings"]))
        web_report_url = _web_report_url(config, period)
        ga4_report_url = _ga4_report_url(config)
        actions = []
        if web_report_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看可视化日报"},
                "type": "primary",
                "url": web_report_url,
            })
        if ga4_report_url:
            actions.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看 GA4 异常明细表"},
                "type": "default" if web_report_url else "primary",
                "url": ga4_report_url,
            })
        elements: list[dict[str, Any]] = [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(overall_lines)}},
        ]
        if actions:
            elements.append({"tag": "action", "actions": actions})
        elements.extend([
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(event_lines)}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(reason_lines)}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(quality_lines)}},
        ])
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {"template": "orange" if daily else "blue", "title": {"tag": "plain_text", "content": f"GA4 业务异常{title_type}｜{period['start_date']}～{period['end_date']}"}},
                "elements": elements,
            },
        }


def build_failure_card(request: ReportRequest) -> dict[str, Any]:
    period = request.report_range
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": "red", "title": {"tag": "plain_text", "content": "GA4 业务异常周报生成失败"}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": f"本次报告未生成成功，请查看本地脱敏日志。\n计划周期：{period.start_date.isoformat()}～{period.end_date.isoformat()}"}}],
        },
    }


class HtmlRenderer:
    def render(self, report: dict[str, Any]) -> str:
        period = report["period"]
        comparison = report.get("comparison_period")
        summary = report["summary"]
        days = _days(period)
        title = f"GA4 业务异常{'日报' if days == 1 else ('周报' if days == 7 else '报告')}"

        def number(value: int | float | None) -> str:
            return "—" if value is None else (f"{value:,.1f}" if isinstance(value, float) else f"{value:,}")

        def change(value: dict[str, Any]) -> str:
            if value["status"] == "new":
                return "新出现"
            if value["delta"] is None:
                return "未比较"
            return "0.0%" if value["delta"] == 0 else f"{value['delta'] * 100:+.1f}%"

        def rate(value: dict[str, Any] | None, outcome_type: str) -> str:
            if not value:
                return "无可靠分母"
            if value["status"] == "unavailable_zero_denominator":
                return "不可用（分母为 0）"
            if value["value"] is None:
                return "不可用"
            label = {"failed": "失败率", "blocked": "阻断率", "degraded": "降级率"}.get(outcome_type, "结果率")
            return f"{label} {value['value'] * 100:.1f}%（{value['numerator']}/{value['denominator']}）"

        def summary_card(label: str, value: dict[str, Any]) -> str:
            previous = f"<span>上期 {number(value['previous'])} · {escape(change(value))}</span>" if comparison else "<span>未设置对比区间</span>"
            return f"<article class='metric-card'><p>{escape(label)}</p><strong>{number(value['value'])}</strong><div>{previous}</div></article>"

        rows: list[str] = []
        for item in report["events"]:
            rows.append(
                "<tr>"
                f"<th scope='row'><code>{escape(item['event_name'])}</code></th>"
                f"<td><span class='badge badge-{escape(item['outcome_type'])}'>{escape(item['outcome_type'])}</span></td>"
                f"<td class='numeric'>{number(item['event_count']['value'])}</td>"
                f"<td class='numeric'>{number(item['affected_users']['value'])}</td>"
                f"<td>{escape(rate(item['rate'], item['outcome_type']))}</td>"
                f"<td>{escape(change(item['event_count']))}</td>"
                "</tr>"
            )
        if not rows:
            rows.append("<tr><td colspan='6' class='empty'>本期未检测到白名单业务异常事件</td></tr>")
        missing = report["quality"]["missing_dimensions"]
        quality_items = [f"未注册原因维度：{'、'.join(escape(value) for value in missing)}"] if missing else []
        quality_items.extend(escape(value) for value in report["quality"]["warnings"])
        quality_html = "".join(f"<li>{value}</li>" for value in dict.fromkeys(quality_items)) or "<li class='ok'>自定义原因维度均可查询，未发现质量告警</li>"
        comparison_text = f"对比周期：{comparison['start_date']}～{comparison['end_date']}" if comparison else "未设置对比周期"
        dashboard_events: list[dict[str, Any]] = []
        for item in report["events"]:
            reasons = item["reasons"]
            event_count = item["event_count"]["value"] or 0
            covered_count = reasons["coverage"].get("numerator") or 0
            dashboard_events.append({
                "event_name": item["event_name"],
                "outcome_type": item["outcome_type"],
                "event_count": event_count,
                "previous_count": item["event_count"].get("previous"),
                "affected_users": item["affected_users"]["value"] or 0,
                "rate": item["rate"],
                "reason_dimension": reasons["dimension"].removeprefix("customEvent:"),
                "reason_status": reasons["status"],
                "reason_coverage": reasons["coverage"].get("value"),
                "missing_reason_count": max(0, event_count - covered_count) if reasons["status"] == "available" else 0,
                "reasons": reasons["items"],
            })
        dashboard_json = json.dumps(dashboard_events, ensure_ascii=False, separators=(",", ":"))
        dashboard_json = dashboard_json.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme:light; --ink:#172033; --muted:#667085; --line:#e5e7eb; --surface:#fff; --canvas:#f5f7fb; --blue:#2457d6; --red:#c0362c; --orange:#ad6500; --green:#137a48; --violet:#7357c7; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--canvas); color:var(--ink); font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    button,select {{ font:inherit; }} button:focus-visible,select:focus-visible {{ outline:3px solid #9db7ff; outline-offset:2px; }} main {{ max-width:1180px; margin:0 auto; padding:40px 24px 56px; }} header {{ margin-bottom:24px; }} .eyebrow {{ color:var(--blue); font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }} h1,h2,h3 {{ margin:0; letter-spacing:-.02em; }} h1 {{ font-size:32px; }} h2 {{ font-size:20px; }} h3 {{ font-size:15px; }} .period,.helper {{ color:var(--muted); margin:8px 0 0; }}
    section {{ margin-top:24px; }} .section-head {{ align-items:end; display:flex; justify-content:space-between; gap:16px; margin-bottom:14px; }} .summary-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }} .metric-card,.panel {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; }} .metric-card {{ padding:18px 20px; }} .metric-card p {{ color:var(--muted); margin:0 0 4px; }} .metric-card strong {{ display:block; font-size:30px; letter-spacing:-.03em; }} .metric-card div {{ color:var(--muted); font-size:13px; margin-top:4px; }}
    .filters {{ align-items:end; display:flex; flex-wrap:wrap; gap:12px; padding:16px; }} .field {{ display:grid; gap:5px; min-width:220px; }} .field label {{ color:var(--muted); font-size:12px; font-weight:700; }} .field select {{ appearance:none; background:var(--surface); border:1px solid #cfd5df; border-radius:8px; color:var(--ink); min-height:40px; padding:8px 34px 8px 10px; }} .filter-note {{ color:var(--muted); font-size:12px; margin:0 0 9px auto; }}
    .chart-grid {{ display:grid; grid-template-columns:minmax(0,1.3fr) minmax(320px,.7fr); gap:14px; }} .chart-card {{ min-height:380px; padding:18px 20px; }} .chart-head {{ align-items:start; display:flex; justify-content:space-between; gap:16px; margin-bottom:18px; }} .chart-head p {{ color:var(--muted); font-size:12px; margin:3px 0 0; }} .chart-value {{ font-size:22px; font-variant-numeric:tabular-nums; font-weight:700; white-space:nowrap; }}
    .ranking {{ display:grid; gap:12px; }} .rank {{ appearance:none; background:transparent; border:0; color:inherit; cursor:pointer; display:grid; gap:5px; padding:0; text-align:left; width:100%; }} .rank-label {{ display:flex; justify-content:space-between; gap:12px; }} .rank-label code {{ overflow:hidden; text-overflow:ellipsis; }} .rank-label span {{ color:var(--muted); font-variant-numeric:tabular-nums; }} .track {{ background:#edf1f7; border-radius:4px; height:12px; overflow:hidden; }} .track span {{ background:var(--blue); border-radius:inherit; display:block; height:100%; min-width:2px; }} .rank[aria-pressed=true] .track span {{ background:var(--red); }}
    .donut-layout {{ align-items:center; display:grid; gap:18px; grid-template-columns:1fr; min-height:260px; }} .donut {{ align-items:center; background:#e9edf3; border-radius:50%; display:flex; height:180px; justify-content:center; margin:auto; position:relative; width:180px; }} .donut::after {{ background:var(--surface); border-radius:50%; content:""; height:106px; position:absolute; width:106px; }} .donut-center {{ font-size:12px; position:relative; text-align:center; z-index:1; }} .donut-center strong {{ display:block; font-size:24px; }} .legend {{ display:grid; gap:9px; list-style:none; margin:0; padding:0; }} .legend li {{ align-items:center; display:grid; gap:8px; grid-template-columns:10px minmax(0,1fr) auto; }} .swatch {{ border-radius:2px; height:10px; width:10px; }} .legend span:last-child {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px; }} .detail-stat {{ background:#f8fafc; border:1px solid var(--line); border-radius:8px; padding:12px; }} .detail-stat span {{ color:var(--muted); display:block; font-size:12px; }} .detail-stat strong {{ display:block; font-size:18px; margin-top:2px; }} .compare {{ display:grid; gap:10px; margin-top:14px; }} .compare-row {{ align-items:center; display:grid; gap:10px; grid-template-columns:48px minmax(0,1fr) 64px; }} .compare-row span:last-child {{ font-variant-numeric:tabular-nums; text-align:right; }}
    .panel {{ overflow:hidden; }} table {{ border-collapse:collapse; width:100%; }} th,td {{ border-bottom:1px solid var(--line); padding:13px 16px; text-align:left; vertical-align:middle; }} thead th {{ background:#f9fafb; color:var(--muted); font-size:12px; font-weight:700; }} tbody tr:last-child th,tbody tr:last-child td {{ border-bottom:0; }} .numeric {{ font-variant-numeric:tabular-nums; white-space:nowrap; }} code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }} .badge {{ border-radius:999px; display:inline-block; font-size:12px; padding:2px 8px; }} .badge-failed {{ background:#fdecec; color:var(--red); }} .badge-blocked {{ background:#fff4df; color:var(--orange); }} .badge-degraded {{ background:#e9f6ee; color:var(--green); }} .empty,.muted {{ color:var(--muted); }} .empty {{ padding:28px; text-align:center; }}
    .reason-context {{ margin-top:14px; }} .reason-context th:first-child {{ width:30%; }} .reason-context .empty {{ text-align:left; }} details summary {{ cursor:pointer; font-weight:700; padding:16px 20px; }} details[open] summary {{ border-bottom:1px solid var(--line); }}
    .quality {{ padding:18px 20px; }} .quality ul {{ margin:0; padding-left:20px; }} .quality li {{ margin:5px 0; }} .quality .ok {{ color:var(--green); }} footer {{ color:var(--muted); font-size:12px; margin-top:28px; }}
    @media (max-width:860px) {{ .chart-grid {{ grid-template-columns:1fr; }} .detail-grid {{ grid-template-columns:repeat(2,1fr); }} }}
    @media (max-width:600px) {{ main {{ padding:28px 14px 44px; }} h1 {{ font-size:26px; }} .summary-grid,.detail-grid {{ grid-template-columns:1fr; }} .field {{ min-width:100%; }} .filter-note {{ margin:0; }} .donut-layout {{ grid-template-columns:1fr; }} .panel {{ overflow-x:auto; }} table {{ min-width:760px; }} }}
  </style>
</head>
<body>
  <main>
    <header><div class="eyebrow">GA4 reliability</div><h1>{escape(title)}</h1><p class="period">统计周期：{escape(period['start_date'])}～{escape(period['end_date'])} · {escape(comparison_text)}</p></header>
    <section class="panel filters" aria-label="报告筛选">
      <div class="field"><label for="outcome-filter">异常类型</label><select id="outcome-filter"><option value="all">全部异常</option></select></div>
      <div class="field"><label for="event-filter">异常事件</label><select id="event-filter"></select></div>
      <p class="filter-note">筛选结果会写入网址；日期区间由生成命令决定。</p>
    </section>
    <section class="summary-grid" aria-label="总体指标">
      {summary_card("异常事件", summary["abnormal_event_count"])}
      {summary_card("影响用户", summary["affected_users"])}
      {summary_card("活跃用户", summary["active_users"])}
    </section>
    <section>
      <div class="section-head"><div><h2>异常分析</h2><p class="helper">点击条形可切换事件，原因占比始终以当前事件总数为分母。</p></div></div>
      <div class="chart-grid">
        <article class="panel chart-card"><div class="chart-head"><div><h3>异常事件排行</h3><p>当前类型内的事件数</p></div><strong class="chart-value" id="ranking-total">—</strong></div><div class="ranking" id="event-ranking"></div></article>
        <article class="panel chart-card" aria-live="polite"><div class="chart-head"><div><h3>异常原因占比</h3><p id="reason-dimension">—</p></div><strong class="chart-value" id="reason-coverage">—</strong></div><div class="donut-layout"><div class="donut" id="reason-donut"><div class="donut-center"><strong id="selected-count">—</strong><span>异常次数</span></div></div><ul class="legend" id="reason-legend"></ul></div></article>
      </div>
    </section>
    <section id="selected-detail" aria-live="polite">
      <div class="section-head"><div><h2 id="selected-event">事件详情</h2><p class="helper">原因上下文显示该原因中计数最高的平台和版本组合。</p></div></div>
      <div class="panel chart-card">
        <div class="detail-grid" id="detail-stats"></div>
        <h3>本期 / 上期事件数</h3><div class="compare" id="period-comparison"></div>
        <div class="panel reason-context"><table><thead><tr><th scope="col">原因</th><th scope="col">次数 / 占比</th><th scope="col">主要平台</th><th scope="col">主要版本</th></tr></thead><tbody id="reason-context"></tbody></table></div>
      </div>
    </section>
    <section><details class="panel"><summary>查看全部异常事件明细</summary><table><thead><tr><th scope="col">事件</th><th scope="col">类型</th><th scope="col">次数</th><th scope="col">影响用户</th><th scope="col">结果率</th><th scope="col">环比</th></tr></thead><tbody>{''.join(rows)}</tbody></table></details></section>
    <section><h2>数据质量</h2><div class="panel quality"><ul>{quality_html}</ul></div></section>
    <footer>report_schema_version {escape(str(report['report_schema_version']))} · rules_version {escape(str(report['rules_version']))}</footer>
  </main>
  <script type="application/json" id="dashboard-data">{dashboard_json}</script>
  <script>
    (() => {{
      const events = JSON.parse(document.getElementById("dashboard-data").textContent);
      const colors = ["#2457d6", "#c0362c", "#ad6500", "#137a48", "#7357c7", "#4b80e6"];
      const labels = {{failed:"失败",blocked:"阻断",degraded:"降级",invalidated:"失效"}};
      const outcome = document.getElementById("outcome-filter");
      const eventSelect = document.getElementById("event-filter");
      const params = new URLSearchParams(location.search);
      const format = value => new Intl.NumberFormat("zh-CN").format(value ?? 0);
      const percent = value => value == null ? "不可用" : `${{(value * 100).toFixed(1)}}%`;
      const make = (tag, className, text) => {{ const node=document.createElement(tag); if(className) node.className=className; if(text != null) node.textContent=text; return node; }};
      [...new Set(events.map(item => item.outcome_type))].forEach(value => {{ const option=make("option", "", labels[value] || value); option.value=value; outcome.append(option); }});

      function filteredEvents() {{ return events.filter(item => outcome.value === "all" || item.outcome_type === outcome.value); }}
      function syncUrl(eventName) {{ const url=new URL(location.href); outcome.value === "all" ? url.searchParams.delete("outcome") : url.searchParams.set("outcome", outcome.value); eventName ? url.searchParams.set("event", eventName) : url.searchParams.delete("event"); history.replaceState(null, "", url); }}
      function refreshEventOptions(preferred) {{
        const visible=filteredEvents(); eventSelect.replaceChildren();
        visible.forEach(item => {{ const option=make("option", "", item.event_name); option.value=item.event_name; eventSelect.append(option); }});
        eventSelect.value=visible.some(item => item.event_name === preferred) ? preferred : (visible[0]?.event_name || "");
        render();
      }}
      function renderRanking(visible, selected) {{
        const root=document.getElementById("event-ranking"); root.replaceChildren();
        const max=Math.max(...visible.map(item => item.event_count), 1);
        document.getElementById("ranking-total").textContent=`${{format(visible.reduce((sum,item)=>sum+item.event_count,0))}} 次`;
        visible.forEach(item => {{
          const button=make("button", "rank"); button.type="button"; button.dataset.event=item.event_name; button.setAttribute("aria-pressed", String(item.event_name === selected.event_name)); button.setAttribute("aria-label", `查看 ${{item.event_name}}，${{format(item.event_count)}} 次`);
          const label=make("div", "rank-label"); label.append(make("code", "", item.event_name), make("span", "", `${{format(item.event_count)}} 次`));
          const track=make("div", "track"); const fill=make("span"); fill.style.width=`${{item.event_count / max * 100}}%`; track.append(fill); button.append(label, track); root.append(button);
        }});
      }}
      function renderDonut(item) {{
        const total=item.event_count;
        const segments=item.reasons.map(reason => ({{name:reason.reason,count:reason.event_count}}));
        if(item.missing_reason_count) segments.push({{name:"未上报或未批准",count:item.missing_reason_count,missing:true}});
        const donut=document.getElementById("reason-donut"); const legend=document.getElementById("reason-legend"); legend.replaceChildren();
        let offset=0; const stops=[];
        segments.forEach((segment,index) => {{ const start=total ? offset/total*100 : 0; offset+=segment.count; const end=total ? offset/total*100 : 0; const color=segment.missing ? "#cfd5df" : colors[index % colors.length]; stops.push(`${{color}} ${{start}}% ${{end}}%`); const row=make("li"); const swatch=make("span","swatch"); swatch.style.background=color; row.append(swatch,make("span","",segment.name),make("span","",`${{format(segment.count)}} · ${{total ? (segment.count/total*100).toFixed(1) : "0.0"}}%`)); legend.append(row); }});
        if(!segments.length) {{ stops.push("#e9edf3 0 100%"); legend.append(make("li","muted",item.reason_status === "available" ? "暂无已批准原因" : "原因维度不可用")); }}
        donut.style.background=`conic-gradient(${{stops.join(",")}})`; document.getElementById("selected-count").textContent=format(total); document.getElementById("reason-dimension").textContent=item.reason_dimension; document.getElementById("reason-coverage").textContent=`覆盖率 ${{percent(item.reason_coverage)}}`;
      }}
      function renderDetail(item) {{
        document.getElementById("selected-event").textContent=item.event_name;
        const rate=item.rate?.value; const rateLabel=labels[item.outcome_type] ? `${{labels[item.outcome_type]}}率` : "结果率";
        const stats=[["异常次数",format(item.event_count)],["影响用户",format(item.affected_users)],[rateLabel,rate == null ? "无可靠分母" : percent(rate)],["原因覆盖率",percent(item.reason_coverage)]];
        const statsRoot=document.getElementById("detail-stats"); statsRoot.replaceChildren(); stats.forEach(([label,value]) => {{ const card=make("div","detail-stat"); card.append(make("span","",label),make("strong","",value)); statsRoot.append(card); }});
        const compare=document.getElementById("period-comparison"); compare.replaceChildren(); const values=[["本期",item.event_count],["上期",item.previous_count]]; const max=Math.max(...values.map(([,value])=>value || 0),1); values.forEach(([label,value]) => {{ const row=make("div","compare-row"); row.append(make("span","",label)); const track=make("div","track"); const fill=make("span"); fill.style.width=`${{(value || 0)/max*100}}%`; track.append(fill); row.append(track,make("span","",value == null ? "—" : format(value))); compare.append(row); }});
        const context=document.getElementById("reason-context"); context.replaceChildren();
        item.reasons.forEach(reason => {{ const row=document.createElement("tr"); [reason.reason,`${{format(reason.event_count)}} / ${{item.event_count ? (reason.event_count/item.event_count*100).toFixed(1) : "0.0"}}%`,reason.platform,reason.app_version].forEach((value,index) => {{ const cell=document.createElement(index===0 ? "th" : "td"); if(index===0) cell.scope="row"; cell.textContent=value; row.append(cell); }}); context.append(row); }});
        if(!item.reasons.length) {{ const row=document.createElement("tr"); const cell=make("td","empty",item.reason_status === "available" ? "暂无已批准原因值" : "原因维度尚未注册"); cell.colSpan=4; row.append(cell); context.append(row); }}
      }}
      function render() {{
        const visible=filteredEvents(); const selected=visible.find(item => item.event_name === eventSelect.value) || visible[0];
        if(!selected) {{ document.getElementById("ranking-total").textContent="0 次"; document.getElementById("event-ranking").append(make("p","muted","本期没有白名单业务异常事件")); document.getElementById("selected-detail").hidden=true; syncUrl(""); return; }}
        document.getElementById("selected-detail").hidden=false; eventSelect.value=selected.event_name; syncUrl(selected.event_name); renderRanking(visible,selected); renderDonut(selected); renderDetail(selected);
      }}
      outcome.addEventListener("change", () => refreshEventOptions("")); eventSelect.addEventListener("change", render); document.getElementById("event-ranking").addEventListener("click", event => {{ const button=event.target.closest("button[data-event]"); if(button) {{ eventSelect.value=button.dataset.event; render(); }} }});
      const requestedOutcome=params.get("outcome"); if([...outcome.options].some(option => option.value === requestedOutcome)) outcome.value=requestedOutcome; refreshEventOptions(params.get("event"));
    }})();
  </script>
</body>
</html>"""


def _days(period: dict[str, str]) -> int:
    from datetime import date

    return (date.fromisoformat(period["end_date"]) - date.fromisoformat(period["start_date"])).days + 1


def _ga4_report_url(config: dict[str, Any] | None) -> str | None:
    if not config or not config.get("ga4_report_url"):
        return None
    url = str(config["ga4_report_url"])
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "analytics.google.com":
        raise ReportError("GA4 report URL must use https://analytics.google.com")
    return url


def _web_report_url(config: dict[str, Any] | None, period: dict[str, str]) -> str | None:
    if not config or not config.get("web_report_base_url"):
        return None
    base_url = str(config["web_report_base_url"])
    if "{local_ip}" in base_url:
        try:
            route = subprocess.run(
                ["/sbin/route", "-n", "get", "default"],
                capture_output=True, text=True, check=True, timeout=5,
            )
            interface = next(line.split(":", 1)[1].strip() for line in route.stdout.splitlines() if line.strip().startswith("interface:"))
            local_ip = subprocess.run(
                ["/usr/sbin/ipconfig", "getifaddr", interface],
                capture_output=True, text=True, check=True, timeout=5,
            ).stdout.strip()
            if not local_ip:
                raise ValueError
        except (OSError, StopIteration, ValueError, subprocess.SubprocessError):
            raise ReportError("Local IPv4 address could not be detected") from None
        base_url = base_url.replace("{local_ip}", local_ip)
    base_url = base_url.rstrip("/") + "/"
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ReportError("Web report base URL must use HTTP or HTTPS")
    folder = period["start_date"] if period["start_date"] == period["end_date"] else f"{period['start_date']}_to_{period['end_date']}"
    return urllib.parse.urljoin(base_url, f"{folder}/daily.html")


def feishu_webhook_url(config: dict[str, Any]) -> str:
    url = str(config.get("feishu_webhook_url", ""))
    parsed = urllib.parse.urlparse(url)
    loopback = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
    if parsed.scheme != "https" and not loopback:
        raise ReportError("Feishu Webhook URL must use HTTPS")
    if not parsed.netloc:
        raise ReportError("Feishu Webhook URL is invalid")
    return url


class FeishuDelivery:
    def send(self, card: dict[str, Any], config: dict[str, Any]) -> None:
        secret = config.get("feishu_secret")
        if not isinstance(secret, str) or not secret:
            raise ReportError("Feishu signing secret is missing")
        timestamp = str(int(time.time()))
        sign = base64.b64encode(hmac.new(f"{timestamp}\n{secret}".encode(), digestmod=hashlib.sha256).digest()).decode()
        request = urllib.request.Request(
            feishu_webhook_url(config),
            data=json.dumps({**card, "timestamp": timestamp, "sign": sign}, ensure_ascii=False).encode(),
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
        if not isinstance(result, dict) or (result.get("code") != 0 and result.get("StatusCode") != 0):
            raise ReportError("Feishu rejected the report")
