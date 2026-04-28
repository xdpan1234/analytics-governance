# Analytics Governance

Shared governance assets for analytics instrumentation across Android and iOS.

## Layout

```text
skills/
  ga4-analytics-instrumentation/
analytics_schema/
  app_boot.yaml
docs/
  tracking-plan.md
  provider-poc-playbook.md
```

## How To Use

- Use `skills/ga4-analytics-instrumentation` when adding, changing, reviewing, or validating production GA4/Firebase Analytics instrumentation.
- Treat `analytics_schema/*.yaml` as the cross-platform machine-readable event contract.
- Treat `docs/tracking-plan.md` as the human-readable source for event ownership, goals, privacy, and verification.
- Treat `docs/provider-poc-playbook.md` as reference documentation only; it is not a Codex skill.

Android and iOS repositories can consume this repo by submodule, subtree, CI sync, or a local copy of the relevant `skills/` folders.

## Workflow

Follow this flow when generating analytics from a product requirement:

1. **Start from the requirement document**
   - Read the product requirement, user journey, success/failure states, and QA acceptance criteria.
   - Identify meaningful business moments instead of logging every button click.
   - Output only an analytics proposal at this stage; do not change App code yet.

2. **Create or update the analytics contract**
   - Add or update `analytics_schema/<module>.yaml`.
   - Define event names, owner, Android/iOS trigger boundaries, required properties, optional properties, allowed enum values, privacy notes, GA4 custom definitions, dashboard usage, and verification steps.
   - Keep Android and iOS event names, parameters, and enum values identical unless the schema explicitly documents a platform difference.

3. **Update the human-readable Tracking Plan**
   - Add the same module to `docs/tracking-plan.md`.
   - Explain the event goal, owner, trigger, properties, platforms, privacy notes, and verification approach in language that product, QA, data, Android, and iOS can all review.
   - Treat this step as the approval surface before implementation.

4. **Review GA4 and privacy rules**
   - Check event names, parameter names, parameter counts, reserved prefixes, string length, and custom definition needs.
   - Remove PII, raw content, raw URLs, stack traces, tokens, precise location, serial numbers, and high-cardinality free text.
   - Prefer stable low-cardinality enums, booleans, counts, durations, and coarse buckets.

5. **Implement Android from the approved contract**
   - Consume the approved `analytics_schema/<module>.yaml` and Tracking Plan section as inputs.
   - Implement through the Android typed analytics contract / tracker.
   - Do not let business or feature code call `FirebaseAnalytics` directly.
   - Add contract tests for GA4 naming, parameter limits, reserved names, and privacy guardrails.

6. **Implement iOS from the same contract**
   - Reuse the same event names, trigger boundaries, required properties, optional properties, and enum values.
   - Implement through the iOS analytics facade / tracker and GA4 adapter.
   - Do not let business code call Firebase `Analytics.logEvent` directly.
   - Add equivalent iOS guardrail tests.

7. **Verify in GA4**
   - Validate Android and iOS events in DebugView first.
   - Confirm both platforms merge under the same event names.
   - Confirm reports can split by `platform`, `environment`, and `build_region`.
   - Register only the custom definitions needed for funnels, retention, path analysis, dashboards, QA, or exports.

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

Use this when the team wants to review the plan before implementation:

```text
按 ga4-analytics-instrumentation skill，基于这个需求文档新增「设备绑定」模块埋点：
<贴需求文档链接或内容>

要求：
1. 先不要改代码，先输出 tracking plan 和 analytics_schema 草案。
2. 事件需要 Android/iOS 双端一致。
3. 检查 GA4 命名、参数、隐私风险和自定义维度建议。
```

Use this after the schema and Tracking Plan are approved, when Android needs to implement the agreed contract:

```text
按 ga4-analytics-instrumentation skill，基于 analytics-governance 中已经批准的协议实现 Android 端埋点。

协议来源：
- analytics_schema/device_binding.yaml
- docs/tracking-plan.md 中「设备绑定」章节

要求：
1. 不重新设计事件名和参数，除非发现协议与 GA4 规则冲突。
2. 在 Android typed analytics contract / tracker 中实现事件，不允许业务代码直接调用 FirebaseAnalytics。
3. 补充 contract tests，覆盖事件名、参数名、参数数量、保留前缀、隐私字段。
4. 给出 DebugView 验证步骤和需要注册的 GA4 custom definitions。
```

Use this after the same contract needs to be implemented on iOS:

```text
按 ga4-analytics-instrumentation skill，基于 analytics-governance 中已经批准的协议实现 iOS 端埋点。

协议来源：
- analytics_schema/device_binding.yaml
- docs/tracking-plan.md 中「设备绑定」章节

要求：
1. iOS 事件名、触发边界、必填参数、可选参数、枚举值必须与 Android/schema 一致。
2. 建立或复用 iOS AnalyticsTracker / AnalyticsEvent / Ga4AnalyticsAdapter，不允许业务代码直接调用 Firebase Analytics.logEvent。
3. 补充 iOS 侧 GA4 命名、参数、隐私 guardrail 测试。
4. 给出 Android/iOS 双端并排 DebugView 验证 checklist，并确认 GA4 Reports 可以按 platform 拆分。
```

## Security

Do not commit provider API keys, project tokens, server URLs, access tokens, or secrets. POC credentials belong in local ignored files, environment variables, or secure CI secret stores.
