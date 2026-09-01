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
    def render(self, report: dict[str, Any]) -> dict[str, Any]:
        period = report["period"]
        comparison = report.get("comparison_period")
        summary = report["summary"]
        title_type = "周报" if comparison and _days(period) == 7 else "报告"
        comparison_label = ("较上周" if title_type == "周报" else "较上期") if comparison else None
        previous_label = "上周" if title_type == "周报" else "上期"
        overall_lines = ["**总体**"]
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
        event_lines = ["**异常事件 Top 10**"]
        if not report["events"]:
            event_lines.append("本周未检测到白名单业务异常事件" if title_type == "周报" else "本期未检测到白名单业务异常事件")
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
        reason_lines = ["**主要原因**"]
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
        quality_lines = ["**数据质量**"]
        missing = report["quality"]["missing_dimensions"]
        quality_lines.append("未注册原因维度：" + "、".join(missing) if missing else "自定义原因维度均可查询")
        quality_lines.extend(dict.fromkeys(report["quality"]["warnings"]))
        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True},
                "header": {"template": "blue", "title": {"tag": "plain_text", "content": f"GA4 业务异常{title_type}｜{period['start_date']}～{period['end_date']}"}},
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(overall_lines)}},
                    {"tag": "hr"},
                    {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(event_lines)}},
                    {"tag": "hr"},
                    {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(reason_lines)}},
                    {"tag": "hr"},
                    {"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(quality_lines)}},
                ],
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
        rows = "".join(
            f"<tr><td>{escape(item['event_name'])}</td><td>{item['event_count']['value']:,}</td><td>{escape(item['outcome_type'])}</td></tr>"
            for item in report["events"]
        )
        return (
            "<!doctype html><meta charset='utf-8'><title>GA4 异常报告</title>"
            "<h1>GA4 业务异常报告</h1>"
            f"<p>{report['period']['start_date']}～{report['period']['end_date']}</p>"
            "<table><thead><tr><th>事件</th><th>次数</th><th>类型</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )


def _days(period: dict[str, str]) -> int:
    from datetime import date

    return (date.fromisoformat(period["end_date"]) - date.fromisoformat(period["start_date"])).days + 1


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
