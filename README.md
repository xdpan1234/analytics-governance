# Analytics Governance

Shared governance assets for production analytics instrumentation across Android and iOS.

## Layout

```text
skills/
  ga4-analytics-instrumentation/
analytics_schema/
  report_rules.yaml
  account.yaml
  app_basic.yaml
  app_support.yaml
  device.yaml
  media.yaml
  translation.yaml
  tutorial.yaml
docs/
  tracking-plan.md
  provider-poc-playbook.md
  ga4-weekly-error-report.md
tools/
  validate_analytics_schema.rb
  ga4_weekly_error_report.py
  ga4_report/
    contracts.py       # 日期与报告指标契约
    request.py         # 动态区间解析
    rules.py           # 版本化规则加载与 Schema 校验
    data.py            # GA4/fixture 数据源适配器
    calculator.py      # 平台无关统计计算
    rendering.py       # JSON/Feishu/HTML 渲染与 Feishu 投递
tests/
  validate_analytics_schema_test.rb
  test_ga4_weekly_error_report.py
```

## How To Use

- Use `skills/ga4-analytics-instrumentation` when adding, changing, reviewing, or validating production GA4/Firebase Analytics instrumentation.
- Treat `analytics_schema/*.yaml` as the cross-platform machine-readable event contract.
- Treat `docs/tracking-plan.md` as the human-readable source for event ownership, goals, privacy, and verification.
- Treat `docs/provider-poc-playbook.md` as reference documentation only; it is not a production event source of truth.
- Use `docs/ga4-weekly-error-report.md` to preview, configure, and schedule the local GA4 abnormal-outcome report.
- Use `analytics_schema/report_rules.yaml` as the versioned abnormal-outcome rule list; do not infer report scope from event-name suffixes.
- Run `ruby tools/validate_analytics_schema.rb` before implementing Android or iOS code from schema.
- When app instrumentation is completed before governance is updated, backfill the governance contract by comparing the typed app event names with `analytics_schema/*.yaml`, then update `docs/tracking-plan.md` and run the validator.
- `device_usage_*` is part of the Device owner contract and stays in `analytics_schema/device.yaml`; do not create a separate `device_usage.yaml` for the current prefix taxonomy.

Android and iOS repositories can consume this repo by submodule, subtree, CI sync, or a local copy of the relevant `skills/` folders.

## Current Implementation Architecture

- Android typed contract lives in `domain:api:analytics`: `AnalyticsEvent`, `AnalyticsEventName`, `AnalyticsParamName`, `AnalyticsParamValue`, `AnalyticsEventSpec`, typed enums, and module reporters.
- Android app infrastructure provides `AnalyticsTracker`, `AnalyticsAdapter`, `Ga4AnalyticsAdapter`, and the common param provider.
- Business, feature, domain, and data code must call module reporters or `AnalyticsTracker`; they must not call `FirebaseAnalytics` directly.
- Common params are injected by the tracker/adapter layer: `platform`, `environment`, `build_region`, `build_type`, `app_version_name`, `app_version_code`.
- Current Android `build_region` rule is `BuildConfig.IS_PRODUCT=true -> us`; non-product builds report `sg`.
- iOS must expose the same facade/adapter shape and use the same event names, params, enum values, and privacy boundaries.

## Workflow

Follow this flow when generating analytics from a product requirement:

1. **Start from the requirement document**
   - Read the product requirement, user journey, success/failure states, and QA acceptance criteria.
   - Identify meaningful business moments instead of logging every button click.
   - Output only an analytics proposal at this stage; do not change App code yet.

2. **Create or update the analytics contract**
   - Add or update `analytics_schema/<module>.yaml` using `schema_version: 2`.
   - Define event names, owner, Android/iOS trigger boundaries, required properties, optional properties, allowed enum values, privacy notes, GA4 custom definitions, dashboard usage, and verification steps.
   - Add `ga4_custom_metrics` only for numeric params that should become GA4 custom metrics, such as a future `*_duration_ms` on a terminal event.
   - Keep Android and iOS event names, parameters, and enum values identical unless the schema explicitly documents a platform difference.

3. **Update the human-readable Tracking Plan**
   - Add the same module to `docs/tracking-plan.md`.
   - Explain the event goal, owner, trigger, properties, platforms, privacy notes, and verification approach in language that product, QA, data, Android, and iOS can all review.
   - Treat this step as the approval surface before implementation.

4. **Review GA4 and privacy rules**
   - Run `ruby tools/validate_analytics_schema.rb`.
   - Check event names, parameter names, parameter counts, reserved prefixes, string length, and custom definition needs.
   - Remove PII, raw content, raw URLs, stack traces, tokens, precise location, serial numbers, and high-cardinality free text.
   - Prefer stable low-cardinality enums, booleans, counts, durations, and coarse buckets.

5. **Implement Android from the approved contract**
   - Consume the approved `analytics_schema/<module>.yaml` and Tracking Plan section as inputs.
   - Implement through the Android typed analytics contract, module reporter, and tracker.
   - Add or update `AnalyticsEventName`, `AnalyticsEventSpec`, typed enums, reporter APIs, and reporter/contract tests.
   - Do not let business or feature code call `FirebaseAnalytics` directly.

6. **Implement iOS from the same contract**
   - Reuse the same event names, trigger boundaries, required properties, optional properties, and enum values.
   - Implement through the iOS analytics facade/tracker and GA4 adapter.
   - Do not let business code call Firebase `Analytics.logEvent` directly.
   - Add equivalent iOS guardrail tests.

7. **Verify in GA4**
   - Validate Android and iOS events in DebugView first.
   - Confirm both platforms merge under the same event names.
   - Confirm reports can split by `platform`, `environment`, and `build_region`.
   - Register only the custom definitions and metrics needed for funnels, retention, path analysis, dashboards, QA, or exports.

## Request Examples

Use this when a new product requirement needs a formal analytics module:

```text
按 ga4-analytics-instrumentation skill，读取这个需求文档，给「语音聊天」模块新增正式 GA4 埋点方案，先只改 analytics-governance 仓库，不改 App 代码。

需求文档：
https://xxx

输出：
- analytics_schema/chat_voice.yaml
- docs/tracking-plan.md 中对应章节
- GA4 custom definitions 建议
- Android/iOS 验证 checklist
```

Use this after the schema and Tracking Plan are approved, when Android needs to implement the agreed contract:

```text
按 ga4-analytics-instrumentation skill，基于 analytics-governance 中已经批准的协议实现 Android 端埋点。

协议来源：
- analytics_schema/app_basic.yaml
- docs/tracking-plan.md 中「App Basic」章节

要求：
1. 先运行 ruby tools/validate_analytics_schema.rb，schema 不通过时先修协议，不写 App 代码。
2. 参考现有 app_basic 实现方式：AnalyticsEventName、AnalyticsEventSpec、AnalyticsParamName、typed enum、AppBasicAnalyticsReporter、DefaultAnalyticsTracker、Ga4AnalyticsAdapter、Ga4AnalyticsMapper。
3. 不重新设计事件名、参数名、枚举值和触发边界，除非发现协议与 GA4 规则冲突。
4. 在 Android typed analytics contract / tracker 中实现事件，不允许业务代码直接调用 FirebaseAnalytics。
5. 补充 reporter tests 和 contract tests，覆盖事件名、参数名、参数数量、保留前缀、隐私字段、reporter 输出。
6. 给出 DebugView 验证步骤和需要注册的 GA4 custom definitions。
```

Use this after the same contract needs to be implemented on iOS:

```text
按 ga4-analytics-instrumentation skill，基于 analytics-governance 中已经批准的协议实现 iOS 端埋点。

协议来源：
- analytics_schema/app_basic.yaml
- docs/tracking-plan.md 中「App Basic」章节

要求：
1. 先运行 ruby tools/validate_analytics_schema.rb，schema 不通过时先修协议，不写 App 代码。
2. 参考现有 app_basic 实现方式：AnalyticsEventName、AnalyticsEventSpec、AnalyticsParamName、typed Swift enum、AppBasicAnalyticsReporter、DefaultAnalyticsTracker、Ga4AnalyticsAdapter、Ga4AnalyticsMapper。
3. iOS 事件名、触发边界、必填参数、可选参数、枚举值必须与 Android/schema 一致。
4. 建立或复用 iOS AnalyticsTracker / AnalyticsEvent / Ga4AnalyticsAdapter，不允许业务代码直接调用 Firebase Analytics.logEvent。
5. 补充 iOS 侧 reporter tests 和 GA4 命名、参数、隐私 guardrail 测试。
6. 给出 Android/iOS 双端并排 DebugView 验证 checklist，并确认 GA4 Reports 可以按 platform 拆分。
```

Use this when both platform implementations should be generated after the governance contract is approved:

```text
按 ga4-analytics-instrumentation skill，基于 analytics-governance 的 app_basic 协议生成双端埋点代码方案并实现。

协议来源：
- analytics_schema/app_basic.yaml
- docs/tracking-plan.md 中「App Basic」章节

要求：
1. 先运行 ruby tools/validate_analytics_schema.rb。
2. Android 参考 domain:api:analytics 的 AppBasicAnalyticsReporter 路径，实现 typed contract、reporter、mapper、adapter 边界和测试。
3. iOS 参考 VoiceAssistant/General/Analytics/AppBasicAnalyticsReporter.swift 路径，实现 AnalyticsEvent、reporter、mapper、adapter 边界和测试。
4. Android/iOS 必须使用同一套 event_name、param name、allowed_values 和 privacy_notes。
5. 不允许业务代码直接调用 FirebaseAnalytics 或 Firebase Analytics.logEvent。
```

## Security

Do not commit provider API keys, project tokens, server URLs, access tokens, or secrets. POC credentials belong in local ignored files, environment variables, or secure CI secret stores.
