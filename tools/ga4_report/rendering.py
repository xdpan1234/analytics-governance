from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
        if not report["events"]:
            event_lines.append({"日报": "昨日未检测到白名单业务异常事件", "周报": "本周未检测到白名单业务异常事件"}.get(title_type, "本期未检测到白名单业务异常事件"))
        for index, item in enumerate(report["events"], start=1):
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
        for item in report["events"]:
            reasons = item["reasons"]
            if reasons["status"] != "available":
                reason_lines.append(f"`{item['event_name']}` 覆盖率 unavailable（原因维度未注册）")
                continue
            coverage = reasons["coverage"]
            reason_lines.append(f"`{item['event_name']}` 覆盖率 {coverage['value'] * 100:.1f}%")
            for reason in reasons["items"]:
                share = reason["event_count"] / item["event_count"]["value"] * 100
                reason_lines.append(
                    f"• {reason['reason']}：{reason['event_count']}（{share:.1f}%）；"
                    f"最高上下文 {reason['platform']} / {reason['app_version']}：{reason['context_count']}"
                )
        if not report["events"]:
            reason_lines.append("本期无异常原因需要拆解")
        quality_lines = ["**🩺 数据质量**" if daily else "**数据质量**"]
        missing = report["quality"]["missing_dimensions"]
        quality_lines.append("未注册原因维度：" + "、".join(missing) if missing else "自定义原因维度均可查询")
        quality_lines.extend(dict.fromkeys(report["quality"]["warnings"]))
        elements: list[dict[str, Any]] = [
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(overall_lines)}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(event_lines)}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(reason_lines)}},
        ]
        report_url = _ga4_report_url(config)
        if report_url:
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看 GA4 异常明细表"},
                    "type": "primary",
                    "url": report_url,
                }],
            })
        elements.extend([
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
        title = "GA4 业务异常周报" if comparison and _days(period) == 7 else "GA4 业务异常报告"

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
            previous = f"<span>上期 {number(value['previous'])}</span>" if comparison else "<span>未设置对比区间</span>"
            return f"<article class='metric-card'><p>{escape(label)}</p><strong>{number(value['value'])}</strong><div>{previous}</div></article>"

        rows: list[str] = []
        for item in report["events"]:
            event_count = item["event_count"]["value"] or 0
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
        reason_cards: list[str] = []
        # Reason cards are built in the same pass as event rows to keep display order identical.
        for item in report["events"]:
            reasons = item["reasons"]
            if reasons["status"] != "available":
                reason_body = "<p class='muted'>不可用：原因维度尚未注册。</p>"
                coverage = "不可用"
            else:
                event_count = item["event_count"]["value"] or 0
                coverage_value = reasons["coverage"]["value"] or 0
                coverage = f"{coverage_value * 100:.1f}%"
                reason_items: list[str] = []
                for reason in reasons["items"]:
                    share = reason["event_count"] / event_count * 100 if event_count else 0
                    width = max(0, min(100, share))
                    reason_items.append(
                        "<li>"
                        f"<div class='reason-line'><strong>{escape(reason['reason'])}</strong><span>{reason['event_count']:,} 次 · {share:.1f}%</span></div>"
                        f"<div class='bar' role='progressbar' aria-label='{escape(reason['reason'])} 占比' aria-valuenow='{share:.1f}' aria-valuemin='0' aria-valuemax='100'><span style='width:{width:.1f}%'></span></div>"
                        f"<small>最高上下文：{escape(reason['platform'])} / {escape(reason['app_version'])}（{reason['context_count']:,} 次）</small>"
                        "</li>"
                    )
                reason_body = "<ul class='reason-list'>" + "".join(reason_items or ["<li class='muted'>暂无已批准原因值</li>"]) + "</ul>"
            reason_cards.append(
                "<article class='reason-card'>"
                f"<div class='reason-card-head'><code>{escape(item['event_name'])}</code><span>覆盖率 {coverage}</span></div>"
                f"{reason_body}</article>"
            )
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#667085; --line:#e5e7eb; --surface:#fff; --canvas:#f5f7fb; --blue:#2457d6; --red:#c0362c; --orange:#ad6500; --green:#137a48; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--canvas); color:var(--ink); font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }}
    main {{ max-width:1180px; margin:0 auto; padding:40px 24px 56px; }} header {{ margin-bottom:28px; }} .eyebrow {{ color:var(--blue); font-size:12px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }} h1,h2 {{ margin:0; letter-spacing:-.02em; }} h1 {{ font-size:32px; }} h2 {{ font-size:20px; margin-bottom:16px; }} .period {{ color:var(--muted); margin:8px 0 0; }}
    section {{ margin-top:28px; }} .summary-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }} .metric-card,.panel,.reason-card {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; }} .metric-card {{ padding:18px 20px; }} .metric-card p {{ color:var(--muted); margin:0 0 4px; }} .metric-card strong {{ display:block; font-size:30px; letter-spacing:-.03em; }} .metric-card div {{ color:var(--muted); font-size:13px; margin-top:4px; }}
    .panel {{ overflow:hidden; }} table {{ border-collapse:collapse; width:100%; }} th,td {{ border-bottom:1px solid var(--line); padding:13px 16px; text-align:left; vertical-align:middle; }} thead th {{ background:#f9fafb; color:var(--muted); font-size:12px; font-weight:700; }} tbody tr:last-child th,tbody tr:last-child td {{ border-bottom:0; }} .numeric {{ font-variant-numeric:tabular-nums; white-space:nowrap; }} code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px; }} .badge {{ border-radius:999px; display:inline-block; font-size:12px; padding:2px 8px; }} .badge-failed {{ background:#fdecec; color:var(--red); }} .badge-blocked {{ background:#fff4df; color:var(--orange); }} .badge-degraded {{ background:#e9f6ee; color:var(--green); }} .empty,.muted {{ color:var(--muted); }} .empty {{ padding:28px; text-align:center; }}
    .reason-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }} .reason-card {{ padding:18px 20px; }} .reason-card-head,.reason-line {{ align-items:center; display:flex; justify-content:space-between; gap:12px; }} .reason-card-head {{ border-bottom:1px solid var(--line); padding-bottom:12px; }} .reason-card-head span {{ color:var(--muted); font-size:13px; }} .reason-list {{ list-style:none; margin:0; padding:8px 0 0; }} .reason-list li {{ padding:9px 0; }} .reason-line span,small {{ color:var(--muted); font-size:13px; }} .bar {{ background:#edf1f7; border-radius:4px; height:6px; margin:6px 0; overflow:hidden; }} .bar span {{ background:var(--blue); border-radius:inherit; display:block; height:100%; }}
    .quality {{ padding:18px 20px; }} .quality ul {{ margin:0; padding-left:20px; }} .quality li {{ margin:5px 0; }} .quality .ok {{ color:var(--green); }} footer {{ color:var(--muted); font-size:12px; margin-top:28px; }}
    @media (max-width:760px) {{ main {{ padding:28px 14px 44px; }} h1 {{ font-size:26px; }} .summary-grid,.reason-grid {{ grid-template-columns:1fr; }} .panel {{ overflow-x:auto; }} table {{ min-width:760px; }} }}
  </style>
</head>
<body>
  <main>
    <header><div class="eyebrow">GA4 reliability</div><h1>{escape(title)}</h1><p class="period">统计周期：{escape(period['start_date'])}～{escape(period['end_date'])} · {escape(comparison_text)}</p></header>
    <section class="summary-grid" aria-label="总体指标">
      {summary_card("异常事件", summary["abnormal_event_count"])}
      {summary_card("影响用户", summary["affected_users"])}
      {summary_card("活跃用户", summary["active_users"])}
    </section>
    <section><h2>异常事件 Top 10</h2><div class="panel"><table><thead><tr><th scope="col">事件</th><th scope="col">类型</th><th scope="col">次数</th><th scope="col">影响用户</th><th scope="col">结果率</th><th scope="col">环比</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
    <section><h2>主要错误原因</h2><div class="reason-grid">{''.join(reason_cards) if reason_cards else '<div class="panel reason-card"><p class="muted">本期没有需要拆解的异常原因。</p></div>'}</div></section>
    <section><h2>数据质量</h2><div class="panel quality"><ul>{quality_html}</ul></div></section>
    <footer>report_schema_version {escape(str(report['report_schema_version']))} · rules_version {escape(str(report['rules_version']))}</footer>
  </main>
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
