# GA4 业务异常事件周报

该工具每周读取 GA4 Data API 中正式 Schema 批准的业务失败、阻断、降级和失效事件，计算上一个完整周与前一周的异常量、影响用户、结果率、周环比和主要原因，并发送飞书卡片。

P0 在本地 Mac 运行，不需要 Analytics Admin API、GA4 Administrator、Cloud Run、Cloud Scheduler 或 BigQuery。

## 1. 先预览固定样例

~~~bash
python3 tools/ga4_weekly_error_report.py --fixture examples/ga4_weekly_error_report_fixture.json --preview --as-of 2026-09-01
~~~

预览只向标准输出写入飞书卡片 JSON，不访问 GA4 或飞书。

## 2. 准备个人 OAuth

承载 OAuth 的 Google Cloud Project 需要启用 Analytics Data API。目标 GA4 Property 只需给个人账号只读访问权限。

~~~bash
gcloud auth application-default login --scopes=https://www.googleapis.com/auth/analytics.readonly
~~~

周报通过 gcloud auth application-default print-access-token 刷新个人 ADC，不读取 Analytics Admin API。若 launchd 找不到 gcloud，在本地配置中填写其绝对路径。

## 3. 创建本地私密配置

在仓库外或被 Git 忽略的位置创建 JSON：

~~~json
{
  "property_id": "YOUR_GA4_PROPERTY_ID",
  "report_timezone": "Asia/Shanghai",
  "environment": "prod",
  "data_api_base_url": "YOUR_GA4_DATA_API_BASE_URL",
  "gcloud_bin": "/opt/homebrew/bin/gcloud",
  "feishu_webhook_url": "YOUR_FEISHU_WEBHOOK_URL",
  "feishu_secret": "REPLACE_ME"
}
~~~

`data_api_base_url` 填写 Google 官方文档给出的 GA4 Data API v1beta 端点；也可仅在本地通过 `GA4_DATA_API_BASE_URL` 环境变量提供。

限制文件权限：

~~~bash
chmod 600 /absolute/path/to/ga4-weekly-error-report.json
~~~

environment 可省略，设置时仅允许 `prod`；省略后周报会明确提示数据未按环境过滤。如果配置了该值但 GA4 未注册事件级自定义维度 environment，周报同样不会假装已过滤，而是在数据质量区提示“未应用 environment 过滤”。

## 4. 先手动读取 GA4

只生成本地预览：

~~~bash
python3 tools/ga4_weekly_error_report.py --config /absolute/path/to/ga4-weekly-error-report.json --preview
~~~

确认日期、统计和原因维度后，再发送飞书：

~~~bash
python3 tools/ga4_weekly_error_report.py --config /absolute/path/to/ga4-weekly-error-report.json
~~~

认证、Data API 或响应校验失败时，程序不会发送成功卡片；如果飞书仍可访问，会发送一张脱敏的生成失败卡片并以非零状态退出。成功但没有异常事件时仍会发送零异常周报。

## 5. 安装每周任务

复制 launchd 示例到 ~/Library/LaunchAgents/，替换以下占位符：

- __PYTHON__：python3 的绝对路径。
- __SCRIPT__：周报程序的绝对路径。
- __CONFIG__：权限为 0600 的本地配置绝对路径。
- __REPOSITORY__：本仓库绝对路径。
- __LOG_DIRECTORY__：仅当前用户可访问的日志目录。

示例默认每周一 10:00 按 Mac 本地时间执行。安装前检查：

~~~bash
plutil -lint ~/Library/LaunchAgents/ai.looktech.ga4-weekly-error-report.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.looktech.ga4-weekly-error-report.plist
launchctl kickstart -k gui/$(id -u)/ai.looktech.ga4-weekly-error-report
~~~

launchd 与手动执行使用同一入口、同一配置和同一统计口径。正式启用前，必须先完成个人账号对目标 Property 的生产冒烟验证。

## 数据口径

- failed：failed / (completed + failed)，仅用于显式配置了 completed 事件的流程。
- blocked：blocked / evaluated，仅用于显式配置了 evaluated 事件的流程。
- degraded：degraded / (completed + degraded)。
- 无可靠分母：仅展示次数、影响用户和每千活跃用户次数。
- 原因字段默认使用 failure_reason；Translation 阻断使用 block_reason；设备媒体同步失败使用 error_source。
- 卡片最多展示 Top 10 异常事件和每个事件 Top 3 原因。

自定义参数只有注册为 GA4 事件级自定义维度后，才能通过 customEvent:* 查询，且注册不会回填历史数据。

## 隐私与凭证

不要把 Property ID、OAuth 凭证、飞书 Webhook 或签名 Secret 提交到仓库。周报只允许正式 Schema 中的低基数原因、平台和应用版本，不得发送原始错误、堆栈、请求体、用户内容或设备标识。
