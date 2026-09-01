import base64
import hashlib
import hmac
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "ga4_weekly_error_report.py"


def report_response(dimensions, metrics, rows):
    return {
        "dimensionHeaders": [{"name": name} for name in dimensions],
        "metricHeaders": [{"name": name, "type": "TYPE_INTEGER"} for name in metrics],
        "rows": [
            {
                "dimensionValues": [{"value": value} for value in dimension_values],
                "metricValues": [{"value": str(value)} for value in metric_values],
            }
            for dimension_values, metric_values in rows
        ],
    }


def scalar_response(metrics, value):
    response = report_response([], metrics, [([], [value])])
    response.pop("dimensionHeaders")
    return response


@contextmanager
def feishu_server(response=b'{"code":0}'):
    deliveries = []

    class FeishuHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            deliveries.append(json.loads(self.rfile.read(length)))
            data = response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), FeishuHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/webhook", deliveries
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def write_private_config(directory, webhook_url, secret):
    path = Path(directory) / "report.json"
    path.write_text(
        json.dumps(
            {
                "property_id": "123",
                "report_timezone": "Asia/Shanghai",
                "feishu_webhook_url": webhook_url,
                "feishu_secret": secret,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


class Ga4WeeklyErrorReportTest(unittest.TestCase):
    def test_user_can_preview_weekly_report_from_fixed_data_api_responses(self):
        fixture = {
            "metadata": {
                "dimensions": [
                    {"apiName": "platform"},
                    {"apiName": "appVersion"},
                    {"apiName": "customEvent:failure_reason"},
                    {"apiName": "customEvent:block_reason"},
                    {"apiName": "customEvent:error_source"},
                ]
            },
            "reports": {
                "current": {
                    "outcomes": report_response(
                        ["eventName"],
                        ["eventCount", "totalUsers"],
                        [
                            (["account_login_failed"], [10, 8]),
                            (["account_login_completed"], [90, 70]),
                        ],
                    ),
                    "affected_users": scalar_response(["totalUsers"], 8),
                    "active_users": scalar_response(["activeUsers"], 1000),
                    "reasons": {
                        "customEvent:failure_reason": report_response(
                            [
                                "eventName",
                                "customEvent:failure_reason",
                                "platform",
                                "appVersion",
                            ],
                            ["eventCount"],
                            [
                                (
                                    ["account_login_failed", "network_error", "android", "1.2.0"],
                                    [4],
                                ),
                                (
                                    ["account_login_failed", "network_error", "ios", "1.3.0"],
                                    [2],
                                ),
                                (
                                    ["account_login_failed", "timeout", "ios", "1.3.0"],
                                    [3],
                                ),
                                (
                                    [
                                        "account_login_failed",
                                        "email=user@example.com",
                                        "ios",
                                        "1.3.0",
                                    ],
                                    [1],
                                ),
                            ],
                        )
                    },
                },
                "previous": {
                    "outcomes": report_response(
                        ["eventName"],
                        ["eventCount", "totalUsers"],
                        [
                            (["account_login_failed"], [5, 4]),
                            (["account_login_completed"], [95, 75]),
                        ],
                    ),
                    "affected_users": scalar_response(["totalUsers"], 4),
                    "active_users": scalar_response(["activeUsers"], 800),
                    "reasons": {},
                },
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--fixture",
                    str(fixture_path),
                    "--preview",
                    "--as-of",
                    "2026-09-01",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "msg_type": "interactive",
                "card": {
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "template": "blue",
                        "title": {
                            "tag": "plain_text",
                            "content": "GA4 业务异常周报｜2026-08-24～2026-08-30",
                        },
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    "**总体**\n"
                                    "异常事件：10（上周 5，+100.0%）\n"
                                    "影响用户：8（上周 4）\n"
                                    "活跃用户：1,000\n"
                                    "对比周期：2026-08-17～2026-08-23"
                                ),
                            },
                        },
                        {"tag": "hr"},
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    "**异常事件 Top 10**\n"
                                    "1. `account_login_failed` — 10 次，8 用户；"
                                    "次数环比 +100.0%；"
                                    "失败率 10.0%（10/100），较上周 +5.0 pp"
                                ),
                            },
                        },
                        {"tag": "hr"},
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    "**主要原因**\n"
                                    "`account_login_failed` 覆盖率 90.0%\n"
                                    "• network_error：6（60.0%）；"
                                    "最高上下文 android / 1.2.0：4\n"
                                    "• timeout：3（30.0%）；"
                                    "最高上下文 ios / 1.3.0：3"
                                ),
                            },
                        },
                        {"tag": "hr"},
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": (
                                    "**数据质量**\n"
                                    "自定义原因维度均可查询\n"
                                    "已隐藏未批准原因值：1 次"
                                ),
                            },
                        },
                    ],
                },
            },
        )

    def test_preview_covers_every_approved_abnormal_outcome_without_fake_rates(self):
        abnormal_events = [
            "account_login_failed",
            "account_data_control_failed",
            "account_username_rule_blocked",
            "account_auth_state_invalidated",
            "app_boot_degraded",
            "app_legal_link_open_failed",
            "app_language_fallback_blocked",
            "contact_us_failed",
            "chat_response_failed",
            "chat_voice_start_failed",
            "device_entry_blocked",
            "device_binding_failed",
            "device_setting_update_failed",
            "device_sync_failed",
            "device_reconnect_failed",
            "device_version_gate_blocked",
            "device_ota_failed",
            "device_usage_photo_capture_failed",
            "device_usage_video_record_failed",
            "device_usage_audio_record_failed",
            "device_usage_ai_chat_failed",
            "device_usage_media_sync_failed",
            "media_import_degraded",
            "media_import_failed",
            "media_import_blocked",
            "media_action_failed",
            "media_playback_failed",
            "media_horizon_export_failed",
            "note_recording_failed",
            "note_import_failed",
            "note_processing_failed",
            "notes_setting_failed",
            "note_export_failed",
            "note_delete_failed",
            "note_speaker_label_blocked",
            "reminder_save_failed",
            "reminder_playback_failed",
            "translation_blocked",
            "translation_session_failed",
            "tutorial_help_link_open_failed",
        ]
        denominator_counts = {
            "account_login_completed": 9,
            "account_username_rule_evaluated": 4,
            "app_boot_completed": 9,
            "app_legal_link_opened": 9,
            "contact_us_opened": 9,
            "chat_response_completed": 9,
            "chat_voice_started": 9,
            "device_binding_completed": 9,
            "device_setting_updated": 9,
            "device_sync_completed": 9,
            "device_reconnect_completed": 9,
            "device_version_gate_evaluated": 4,
            "device_ota_completed": 9,
            "device_usage_photo_capture_succeeded": 9,
            "device_usage_video_record_ended": 9,
            "device_usage_audio_record_ended": 9,
            "device_usage_ai_chat_ended": 9,
            "media_import_completed": 9,
            "media_playback_started": 9,
            "note_recording_completed": 9,
            "note_import_completed": 9,
            "note_processing_completed": 9,
            "notes_setting_updated": 9,
            "note_export_completed": 9,
            "note_deleted": 9,
            "note_speaker_label_evaluated": 4,
            "reminder_saved": 9,
            "reminder_playback_started": 9,
            "translation_session_completed": 9,
            "tutorial_help_link_opened": 9,
        }
        current_rows = [
            (
                [event_name],
                [2 if event_name == "device_usage_media_sync_failed" else 1, 1],
            )
            for event_name in abnormal_events
        ]
        current_rows += [
            ([event_name], [count, count])
            for event_name, count in denominator_counts.items()
        ]
        fixture = {
            "metadata": {
                "dimensions": [
                    {"apiName": "platform"},
                    {"apiName": "appVersion"},
                    {"apiName": "customEvent:failure_reason"},
                    {"apiName": "customEvent:error_source"},
                ]
            },
            "reports": {
                "current": {
                    "outcomes": report_response(
                        ["eventName"], ["eventCount", "totalUsers"], current_rows
                    ),
                    "affected_users": report_response([], ["totalUsers"], [([], [20])]),
                    "active_users": report_response([], ["activeUsers"], [([], [100])]),
                    "reasons": {
                        "customEvent:error_source": report_response(
                            [
                                "eventName",
                                "customEvent:error_source",
                                "platform",
                                "appVersion",
                            ],
                            ["eventCount"],
                            [
                                (
                                    [
                                        "device_usage_media_sync_failed",
                                        "network",
                                        "ios",
                                        "2.0.0",
                                    ],
                                    [2],
                                )
                            ],
                        )
                    },
                },
                "previous": {
                    "outcomes": report_response(
                        ["eventName"], ["eventCount", "totalUsers"], []
                    ),
                    "affected_users": report_response([], ["totalUsers"], [([], [0])]),
                    "active_users": report_response([], ["activeUsers"], [([], [100])]),
                    "reasons": {},
                },
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--fixture",
                    str(fixture_path),
                    "--preview",
                    "--as-of",
                    "2026-09-01",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        content = "\n".join(
            element.get("text", {}).get("content", "")
            for element in card["card"]["elements"]
        )
        self.assertIn("异常事件：41（上周 0，new）", content)
        event_content = card["card"]["elements"][2]["text"]["content"]
        self.assertEqual(
            sum(line[:1].isdigit() for line in event_content.splitlines()),
            10,
        )
        self.assertNotIn("tutorial_help_link_open_failed", event_content)
        self.assertIn(
            "`device_usage_media_sync_failed` 覆盖率 100.0%\n"
            "• network：2（100.0%）；最高上下文 ios / 2.0.0：2",
            content,
        )
        self.assertIn(
            "`account_username_rule_blocked` — 1 次，1 用户；"
            "次数环比 new；阻断率 25.0%（1/4），较上周 unavailable",
            content,
        )
        self.assertIn(
            "`app_boot_degraded` — 1 次，1 用户；次数环比 new；"
            "降级率 10.0%（1/10），较上周 unavailable",
            content,
        )
        self.assertIn(
            "`account_auth_state_invalidated` — 1 次，1 用户；"
            "次数环比 new；每千活跃用户 10.0 次",
            content,
        )
        self.assertIn(
            "`account_data_control_failed` — 1 次，1 用户；次数环比 new；"
            "失败率 100.0%（1/1），较上周 unavailable",
            content,
        )
        self.assertIn(
            "未注册原因维度：customEvent:block_reason",
            content,
        )

    def test_preview_marks_zero_evaluated_denominator_and_missing_reason_dimension_unavailable(self):
        fixture = {
            "metadata": {
                "dimensions": [
                    {"apiName": "platform"},
                    {"apiName": "appVersion"},
                    {"apiName": "customEvent:failure_reason"},
                ]
            },
            "reports": {
                period: {
                    "outcomes": report_response(
                        ["eventName"],
                        ["eventCount", "totalUsers"],
                        [
                            (["account_username_rule_blocked"], [1, 1]),
                            (["translation_blocked"], [1, 1]),
                        ] if period == "current" else [],
                    ),
                    "affected_users": report_response(
                        [], ["totalUsers"], [([], [1 if period == "current" else 0])]
                    ),
                    "active_users": report_response([], ["activeUsers"], [([], [0])]),
                    "reasons": {},
                }
                for period in ("current", "previous")
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--fixture",
                    str(fixture_path),
                    "--preview",
                    "--as-of",
                    "2026-09-01",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        content = json.dumps(json.loads(result.stdout), ensure_ascii=False)
        self.assertIn("阻断率 unavailable（分母为 0）", content)
        self.assertIn(
            "`translation_blocked` — 1 次，1 用户；次数环比 new；"
            "每千活跃用户 unavailable（活跃用户为 0）",
            content,
        )
        self.assertIn(
            "`translation_blocked` 覆盖率 unavailable（原因维度未注册）",
            content,
        )

    def test_user_can_preview_report_from_data_api_with_personal_access_token(self):
        requests = []
        metadata = {
            "dimensions": [
                {"apiName": "platform"},
                {"apiName": "appVersion"},
                {"apiName": "customEvent:failure_reason"},
                {"apiName": "customEvent:block_reason"},
                {"apiName": "customEvent:error_source"},
                {"apiName": "customEvent:environment"},
            ]
        }
        class DataApiHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(("GET", self.path, self.headers, None))
                self.send_json(metadata)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                requests.append(("POST", self.path, self.headers, body))
                dimensions = [item["name"] for item in body.get("dimensions", [])]
                metrics = [item["name"] for item in body.get("metrics", [])]
                start_date = body["dateRanges"][0]["startDate"]
                current = start_date == "2026-08-24"
                if dimensions == ["eventName"] and metrics == [
                    "eventCount",
                    "totalUsers",
                ]:
                    rows = [
                        (["account_login_failed"], [10 if current else 5, 8 if current else 4]),
                        (["account_login_completed"], [90 if current else 95, 70 if current else 75]),
                    ]
                    self.send_json(
                        report_response(dimensions, metrics, rows)
                    )
                elif metrics == ["totalUsers"]:
                    self.send_json(
                        report_response([], metrics, [([], [8 if current else 4])])
                    )
                elif metrics == ["activeUsers"]:
                    self.send_json(
                        report_response([], metrics, [([], [1000 if current else 800])])
                    )
                elif "customEvent:failure_reason" in dimensions and current:
                    self.send_json(
                        report_response(
                            dimensions,
                            ["eventCount"],
                            [
                                (
                                    [
                                        "account_login_failed",
                                        "network_error",
                                        "android",
                                        "1.2.0",
                                    ],
                                    [10],
                                )
                            ],
                        )
                    )
                else:
                    self.send_json(report_response(dimensions, ["eventCount"], []))

            def log_message(self, _format, *_args):
                return

            def send_json(self, payload):
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), DataApiHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config_path = Path(directory) / "report.json"
                config_path.write_text(
                    json.dumps(
                        {
                            "property_id": "123",
                            "report_timezone": "Asia/Shanghai",
                            "environment": "prod",
                        }
                    ),
                    encoding="utf-8",
                )
                config_path.chmod(0o600)
                env = os.environ.copy()
                env["GA4_ACCESS_TOKEN"] = "personal-test-token"
                env["GA4_DATA_API_BASE_URL"] = (
                    f"http://127.0.0.1:{server.server_port}/v1beta"
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(config_path),
                        "--preview",
                        "--as-of",
                        "2026-09-01",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env,
                )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(
            card["card"]["header"]["title"]["content"],
            "GA4 业务异常周报｜2026-08-24～2026-08-30",
        )
        self.assertTrue(requests)
        self.assertTrue(
            all(request[2]["Authorization"] == "Bearer personal-test-token" for request in requests)
        )
        requested_ranges = {
            (
                request[3]["dateRanges"][0]["startDate"],
                request[3]["dateRanges"][0]["endDate"],
            )
            for request in requests
            if request[0] == "POST"
        }
        self.assertEqual(
            requested_ranges,
            {("2026-08-24", "2026-08-30"), ("2026-08-17", "2026-08-23")},
        )
        active_user_requests = [
            request[3]
            for request in requests
            if request[0] == "POST"
            and [item["name"] for item in request[3].get("metrics", [])]
            == ["activeUsers"]
        ]
        self.assertTrue(active_user_requests)
        self.assertTrue(
            all(
                "customEvent:environment"
                in json.dumps(request["dimensionFilter"])
                for request in active_user_requests
            )
        )

    def test_data_api_authentication_failure_is_sanitized_and_exits_nonzero(self):
        class UnauthorizedHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401)
                self.end_headers()

            def log_message(self, _format, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), UnauthorizedHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                config_path = Path(directory) / "report.json"
                config_path.write_text(
                    json.dumps(
                        {
                            "property_id": "123",
                            "report_timezone": "Asia/Shanghai",
                        }
                    ),
                    encoding="utf-8",
                )
                config_path.chmod(0o600)
                env = os.environ.copy()
                token = "do-not-log-access-token"
                env["GA4_ACCESS_TOKEN"] = token
                env["GA4_DATA_API_BASE_URL"] = (
                    f"http://127.0.0.1:{server.server_port}/v1beta"
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(config_path),
                        "--preview",
                        "--as-of",
                        "2026-09-01",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env,
                )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Data API request failed with HTTP 401", result.stderr)
        self.assertNotIn(token, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_non_production_environment_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "report.json"
            config_path.write_text(
                json.dumps(
                    {
                        "property_id": "123",
                        "report_timezone": "Asia/Shanghai",
                        "environment": "production",
                    }
                ),
                encoding="utf-8",
            )
            config_path.chmod(0o600)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--config",
                    str(config_path),
                    "--fixture",
                    str(ROOT / "examples" / "ga4_weekly_error_report_fixture.json"),
                    "--preview",
                    "--as-of",
                    "2026-09-01",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr,
            "error: config environment must be prod when set\n",
        )

    def test_user_can_send_signed_weekly_report_to_feishu(self):
        with feishu_server() as (webhook_url, deliveries):
            fixture = {
                "metadata": {
                    "dimensions": [
                        {"apiName": "platform"},
                        {"apiName": "appVersion"},
                        {"apiName": "customEvent:failure_reason"},
                        {"apiName": "customEvent:block_reason"},
                        {"apiName": "customEvent:error_source"},
                    ]
                },
                "reports": {
                    "current": {
                        "outcomes": report_response(
                            ["eventName"],
                            ["eventCount", "totalUsers"],
                            [
                                (["account_login_failed"], [1, 1]),
                                (["account_login_completed"], [9, 8]),
                            ],
                        ),
                        "affected_users": report_response([], ["totalUsers"], [([], [1])]),
                        "active_users": report_response([], ["activeUsers"], [([], [100])]),
                        "reasons": {},
                    },
                    "previous": {
                        "outcomes": report_response(
                            ["eventName"], ["eventCount", "totalUsers"], []
                        ),
                        "affected_users": report_response([], ["totalUsers"], [([], [0])]),
                        "active_users": report_response([], ["activeUsers"], [([], [100])]),
                        "reasons": {},
                    },
                },
            }
            with tempfile.TemporaryDirectory() as directory:
                fixture_path = Path(directory) / "fixture.json"
                fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
                secret = "local-test-secret"
                config_path = write_private_config(directory, webhook_url, secret)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(config_path),
                        "--fixture",
                        str(fixture_path),
                        "--as-of",
                        "2026-09-01",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(deliveries), 1)
        delivery = deliveries[0]
        string_to_sign = (
            f"{delivery['timestamp']}\nlocal-test-secret".encode("utf-8")
        )
        expected_sign = base64.b64encode(
            hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
        ).decode()
        self.assertEqual(delivery["sign"], expected_sign)
        self.assertEqual(delivery["msg_type"], "interactive")
        self.assertEqual(
            delivery["card"]["header"]["title"]["content"],
            "GA4 业务异常周报｜2026-08-24～2026-08-30",
        )

    def test_feishu_rejection_exits_nonzero_without_leaking_secret(self):
        secret = "rejected-report-secret"
        with feishu_server(b'{"code":19021,"msg":"rejected"}') as (webhook_url, _):
            with tempfile.TemporaryDirectory() as directory:
                config_path = write_private_config(directory, webhook_url, secret)
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(config_path),
                        "--fixture",
                        str(ROOT / "examples" / "ga4_weekly_error_report_fixture.json"),
                        "--as-of",
                        "2026-09-01",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Feishu rejected the report", result.stderr)
        self.assertNotIn(secret, result.stderr)

    def test_launchd_template_runs_the_report_every_monday_without_secrets(self):
        path = (
            ROOT
            / "tools"
            / "launchd"
            / "ai.looktech.ga4-weekly-error-report.plist.example"
        )
        with path.open("rb") as source:
            template = plistlib.load(source)

        self.assertEqual(
            template["ProgramArguments"],
            ["__PYTHON__", "__SCRIPT__", "--config", "__CONFIG__"],
        )
        self.assertEqual(
            template["StartCalendarInterval"],
            {"Weekday": 1, "Hour": 10, "Minute": 0},
        )
        self.assertNotIn("secret", json.dumps(template).lower())
        with feishu_server() as (webhook_url, deliveries):
            with tempfile.TemporaryDirectory() as directory:
                secret = "launchd-test-secret"
                config_path = write_private_config(directory, webhook_url, secret)
                working_directory = template["WorkingDirectory"].replace(
                    "__REPOSITORY__", str(ROOT)
                )
                stdout_path = Path(
                    template["StandardOutPath"].replace(
                        "__LOG_DIRECTORY__", directory
                    )
                )
                stderr_path = Path(
                    template["StandardErrorPath"].replace(
                        "__LOG_DIRECTORY__", directory
                    )
                )
                arguments = [
                    {
                        "__PYTHON__": sys.executable,
                        "__SCRIPT__": str(SCRIPT),
                        "__CONFIG__": str(config_path),
                    }.get(argument, argument)
                    for argument in template["ProgramArguments"]
                ]
                arguments += [
                    "--fixture",
                    str(ROOT / "examples" / "ga4_weekly_error_report_fixture.json"),
                    "--as-of",
                    "2026-09-01",
                ]
                with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
                    "w", encoding="utf-8"
                ) as stderr:
                    result = subprocess.run(
                        arguments,
                        cwd=working_directory,
                        stdout=stdout,
                        stderr=stderr,
                        text=True,
                        check=False,
                    )

                stdout = stdout_path.read_text(encoding="utf-8")
                stderr = stderr_path.read_text(encoding="utf-8")

        self.assertEqual(result.returncode, 0, stderr)
        self.assertEqual(stdout, "sent GA4 weekly abnormal-outcome report\n")
        self.assertEqual(stderr, "")
        self.assertEqual(len(deliveries), 1)
        self.assertNotIn(secret, stdout + stderr)

    def test_generation_failure_sends_sanitized_feishu_card_and_exits_nonzero(self):
        with feishu_server() as (webhook_url, deliveries):
            with tempfile.TemporaryDirectory() as directory:
                fixture_path = Path(directory) / "fixture.json"
                fixture_path.write_text(
                    '{"metadata":{},"reports":{"private_raw_response":"do-not-send"}}',
                    encoding="utf-8",
                )
                config_path = write_private_config(
                    directory,
                    webhook_url,
                    "do-not-log-secret",
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--config",
                        str(config_path),
                        "--fixture",
                        str(fixture_path),
                        "--as-of",
                        "2026-09-01",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(deliveries), 1)
        failure_card = deliveries[0]["card"]
        self.assertEqual(failure_card["header"]["template"], "red")
        self.assertEqual(
            failure_card["header"]["title"]["content"],
            "GA4 业务异常周报生成失败",
        )
        serialized = json.dumps(deliveries[0], ensure_ascii=False)
        self.assertNotIn("private_raw_response", serialized)
        self.assertNotIn("do-not-send", serialized)
        self.assertNotIn("do-not-log-secret", result.stderr)

    def test_successful_empty_week_produces_explicit_zero_abnormal_report(self):
        empty_outcomes = report_response(
            ["eventName"], ["eventCount", "totalUsers"], []
        )
        fixture = {
            "metadata": {
                "dimensions": [
                    {"apiName": "platform"},
                    {"apiName": "appVersion"},
                    {"apiName": "customEvent:failure_reason"},
                    {"apiName": "customEvent:block_reason"},
                    {"apiName": "customEvent:error_source"},
                ]
            },
            "reports": {
                period: {
                    "outcomes": empty_outcomes,
                    "affected_users": report_response(
                        [], ["totalUsers"], [([], [0])]
                    ),
                    "active_users": report_response(
                        [], ["activeUsers"], [([], [50])]
                    ),
                    "reasons": {},
                }
                for period in ("current", "previous")
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "fixture.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--fixture",
                    str(fixture_path),
                    "--preview",
                    "--as-of",
                    "2026-09-01",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        serialized = json.dumps(json.loads(result.stdout), ensure_ascii=False)
        self.assertIn("异常事件：0（上周 0，0.0%）", serialized)
        self.assertIn("本周未检测到白名单业务异常事件", serialized)

    def test_malformed_data_api_shape_never_becomes_success_or_traceback(self):
        for malformed_outcomes in ({}, None):
            with self.subTest(malformed_outcomes=malformed_outcomes):
                fixture = {
                    "metadata": {"dimensions": []},
                    "reports": {
                        "current": {
                            "outcomes": malformed_outcomes,
                            "affected_users": report_response(
                                [], ["totalUsers"], [([], [0])]
                            ),
                            "active_users": report_response(
                                [], ["activeUsers"], [([], [0])]
                            ),
                            "reasons": {},
                        },
                        "previous": {
                            "outcomes": report_response(
                                ["eventName"], ["eventCount", "totalUsers"], []
                            ),
                            "affected_users": report_response(
                                [], ["totalUsers"], [([], [0])]
                            ),
                            "active_users": report_response(
                                [], ["activeUsers"], [([], [0])]
                            ),
                            "reasons": {},
                        },
                    },
                }
                with tempfile.TemporaryDirectory() as directory:
                    fixture_path = Path(directory) / "fixture.json"
                    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            "--fixture",
                            str(fixture_path),
                            "--preview",
                            "--as-of",
                            "2026-09-01",
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        check=False,
                    )

                self.assertEqual(result.returncode, 1)
                self.assertTrue(result.stderr.startswith("error: "))
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
