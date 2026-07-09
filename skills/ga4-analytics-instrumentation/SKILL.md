---
name: ga4-analytics-instrumentation
description: Use when adding, changing, reviewing, or validating GA4/Firebase Analytics events, event parameters, user properties, dashboards, exports, or Android/iOS analytics instrumentation.
---

# GA4 Analytics Instrumentation

## Overview

The Tracking Plan and analytics schema are the source of truth for production analytics semantics. GA4/Firebase limits are hard gates, but event names, trigger timing, properties, privacy notes, and verification criteria must be approved before production code is written.

Business code must call a typed analytics contract and tracker. Keep Firebase SDK usage behind an app/infrastructure adapter so Android and iOS can share event semantics and later route to other providers.

## Business Logic Safety

Analytics instrumentation must be non-invasive. Treat reporting as an observation side effect, not a reason to rewrite or reinterpret already verified product behavior.

Rules:

- Do not change existing business decisions, state transitions, navigation, validation, retry behavior, error handling, persistence, network calls, threading, or coroutine/async timing just to add analytics.
- Add reporter calls at approved trigger boundaries with the smallest local edit that preserves the original control flow.
- Do not move business logic into analytics reporters, adapters, mappers, or enum helpers.
- Do not make product behavior depend on analytics success. Tracker and adapter failures must be swallowed or isolated so reporting cannot block, crash, retry, navigate, or change user-visible results.
- If an analytics requirement appears to need business-flow refactoring, stop and propose a separate product/engineering change before implementing instrumentation.
- When touching a previously verified flow, run existing feature tests in addition to analytics reporter/contract tests. Add a regression test if the insertion point is in a sensitive path such as login, binding, payment, permissions, media import, or data deletion.

## Source Of Truth

Before changing a formal event, check:

- `analytics_schema/*.yaml` for the machine-readable event contract.
- `docs/tracking-plan.md` for ownership, purpose, reporting, and verification notes.
- The active product Tracking Plan if it lives in Feishu or another planning system.

If sources disagree, do not silently rename or reinterpret events in code. Update the Tracking Plan/schema or propose a migration first.

`analytics_schema/app_login.yaml` has been removed. Login and auth-state restoration belong to `analytics_schema/account.yaml` through `account_login_*`. Do not use `app_login_*` as a new implementation source and do not double-send old and new login events for the same behavior.

When production analytics already exists in app code and the governance repo is behind, treat the typed app contract as the compatibility source for a backfill pass: compare Android `AnalyticsEventName.value` or the iOS equivalent against `analytics_schema/*.yaml`, add missing events to the existing owner schema, then update `docs/tracking-plan.md`. Do not rename app events during this backfill unless the Tracking Plan explicitly approves a migration.

`device_usage_*` events remain under `analytics_schema/device.yaml` with owner `device`; do not create a separate `device_usage.yaml` unless the prefix taxonomy is changed.

## Spec Boundary

Do not write the governance spec into app code. The full event purpose, trigger explanation, privacy notes, dashboard usage, verification checklist, and approval rationale belong only in `analytics_schema/*.yaml`, `docs/tracking-plan.md`, and governance docs.

App code should contain only the minimum executable analytics contract:

- typed event names;
- typed parameter names;
- event specs with required/optional param sets;
- typed enum values and mappers;
- reporter APIs and tests.

Do not copy long Tracking Plan text, YAML blocks, dashboard descriptions, privacy review prose, or DebugView checklist text into Android/iOS source comments, constants, string resources, or generated code. If code needs context, use a short comment pointing back to the governance schema or Tracking Plan instead.

## GA4 Hard Rules

| Item | GA4/Firebase rule | Project rule |
| --- | --- | --- |
| Event name | Case-sensitive, max 40 chars, starts with a letter, letters/numbers/underscores only | Lower snake case; approved canonical name or ownership prefix |
| Event params | Max 25 params per event | Keep params low-cardinality and analysis-ready |
| Param name | Max 40 chars | Lower snake case, starts with a letter, no leading underscore |
| String param value | Usually max 100 chars | Prefer enums, booleans, counts, durations, coarse buckets |
| User property | Name max 24 chars, value max 36 chars | Stable segmentation fields only |
| Custom definitions/metrics | Limited slots | Register only fields used in reports, funnels, retention, QA, exports, or dashboards |

Reserved prefixes for events, params, and user properties:

- `firebase_`
- `google_`
- `ga_`

Reserved starts for params and user properties:

- `_`
- `gtag.`

Reserved names change. Check official GA4/Firebase docs before adding a new event, param, user property, or custom definition.

## Prefix Taxonomy

Use approved ownership prefixes for new formal events:

| Prefix | Owner | Examples |
| --- | --- | --- |
| `app_` | App shell, lifecycle, cold/warm start, foreground/background | `app_boot_completed`, `app_boot_degraded` |
| `device_` | Glasses/device lifecycle, BLE, binding, connection, firmware | `device_binding_completed` |
| `account_` | Login, signup, profile, subscription/account state | `account_login_completed` |
| `chat_` | Voice chat, text chat, AI response lifecycle | `chat_voice_completed` |
| `media_` | Gallery/media import, capture, sync | `media_import_completed` |
| `note_` | Notes import, creation, detail usage | `note_import_completed` |
| `reminder_` | Reminder creation, alert, completion | `reminder_alert_triggered` |
| `tutorial_` | First-run tutorial, tutorial center, tutorial media, help links | `tutorial_onboarding_completed` |
| `translation_` | Translation setup, session lifecycle, blocking, history | `translation_session_started` |

If two prefixes seem plausible, choose the system that produces the event. Binding a pair of glasses is `device_binding_completed`, not `app_binding_completed`.

`contact_us_*` remains an approved Contact us naming exception unless a future Tracking Plan explicitly migrates it.

## Schema Version 2

Each active YAML schema must include:

- `schema_version: 2`
- `owner`
- `platforms`
- `common_properties.injected_by_adapter`
- `common_properties.definitions`
- `implementation_contract`
- `events`

Each production event must include:

- `event_name`
- `goal`
- `recommended_or_custom`
- `key_event`
- `trigger_android`
- `trigger_ios`
- `required_properties`
- `optional_properties`
- `allowed_values`
- `privacy_notes`
- `ga4_custom_definitions`
- `dashboard_usage`
- `verification_android`
- `verification_ios`

Use optional `ga4_custom_metrics` only when an event actually sends a numeric analysis parameter. For elapsed-time analysis, prefer a duration metric on the terminal event, such as `*_duration_ms`, rather than relying on GA4 UI to pair a start event with an end event.

Run the repository validator before App code generation:

```bash
ruby tools/validate_analytics_schema.rb
```

## Android Architecture

Current Android implementation shape:

```text
domain:api:analytics
  AnalyticsEvent
  AnalyticsEventName(value, spec)
  AnalyticsParamName
  AnalyticsParamValue
  AnalyticsEventSpec
  typed enums
  module reporters

app analytics infrastructure
  AnalyticsTracker
  DefaultAnalyticsTracker
  AnalyticsAdapter
  Ga4AnalyticsAdapter
  AnalyticsCommonParamProvider
```

Rules:

- Module reporters construct typed `AnalyticsEvent` values.
- `DefaultAnalyticsTracker` injects common params and dispatches to provider adapters.
- `Ga4AnalyticsAdapter` is the Android boundary that maps typed events to Firebase `logEvent`.
- Feature, business, domain, and data code must not import or call `FirebaseAnalytics` directly.
- Current Android common params are `platform`, `environment`, `build_region`, `build_type`, `app_version_name`, `app_version_code`.
- Current Android `build_region` rule is `BuildConfig.IS_PRODUCT=true -> us`; non-product builds report `sg`.

## Generate Android Code From Schema

Use this mapping when an approved schema needs Android implementation. For `analytics_schema/app_basic.yaml`, mirror the current Android shape:

| Schema field | Android target |
| --- | --- |
| `events[].event_name` | `AnalyticsEventName` value, such as `APP_LEGAL_LINK_OPENED("app_legal_link_opened", spec)` |
| `required_properties` / `optional_properties` | `AnalyticsEventSpec(requiredProperties, optionalProperties)` |
| property names | `AnalyticsParamName`, such as `ENTRY_POINT("entry_point")` |
| `allowed_values` | typed enums and `toParamValue()` mappers, such as `AnalyticsEntryPoint`, `AnalyticsSurface`, `AnalyticsTriggerSource`, `AnalyticsFailureReason` |
| event trigger | module reporter method, such as `AppBasicAnalyticsReporter.reportLegalLinkOpened(...)` |
| common params | `AnalyticsCommonParamProvider`; do not add them inside reporters |
| provider dispatch | `DefaultAnalyticsTracker` -> `Ga4AnalyticsAdapter` -> Firebase `logEvent` |

Android implementation rules:

- Put shared event types, specs, params, enum values, and module reporters in `domain:api:analytics`.
- Keep Firebase usage inside the app-level `Ga4AnalyticsAdapter`; feature, business, domain, and data code must not import `FirebaseAnalytics`.
- Reporter methods should only send fields defined by the schema. Example: `app_legal_link_opened` sends `entry_point`, `surface`, and optional `trigger_source`.
- Do not copy full schema/Tracking Plan prose into Android source. Keep Android code to typed names, specs, enums, reporters, mappers, and tests; reference governance docs for long-form intent and verification text.
- Adding a reporter call must not alter the original method's branching, return value, exception behavior, state writes, or async scheduling.
- Add reporter tests and contract tests covering event names, param names, param count including common params, reserved prefixes, privacy fields, and reporter output.

## Generate iOS Code From Schema

Use the same approved schema for iOS. For `analytics_schema/app_basic.yaml`, mirror the current iOS shape:

| Schema field | iOS target |
| --- | --- |
| `events[].event_name` | `AnalyticsEventName` case raw value, such as `.legalLinkOpened = "app_legal_link_opened"` |
| `required_properties` / `optional_properties` | `AnalyticsEventSpec(requiredProperties, optionalProperties)` |
| property names | `AnalyticsParamName`, such as `.entryPoint = "entry_point"` |
| `allowed_values` | typed Swift enums, such as `AnalyticsEntryPoint`, `AnalyticsSurface`, `AnalyticsTriggerSource`, `AnalyticsFailureReason` |
| event trigger | module reporter method, such as `AppBasicAnalyticsReporter.reportLegalLinkOpened(...)` |
| common params | `AppAnalyticsCommonParamProvider`; do not add them inside reporters |
| provider dispatch | `DefaultAnalyticsTracker` -> `Ga4AnalyticsAdapter` -> Firebase `Analytics.logEvent` |

iOS implementation rules:

- Reuse event names, trigger boundaries, required params, optional params, enum values, and privacy rules exactly as approved in schema.
- Keep Firebase usage inside `Ga4AnalyticsAdapter`; app/business code must use the analytics facade, reporter, or `AnalyticsTracker`.
- Reporter methods should only send schema-defined fields. Example: `app_legal_link_opened` sends `entry_point`, `surface`, and optional `trigger_source`.
- Do not copy full schema/Tracking Plan prose into iOS source. Keep iOS code to typed names, specs, enums, reporters, mappers, and tests; reference governance docs for long-form intent and verification text.
- Adding a reporter call must not alter the original method's branching, return value, error handling, state writes, navigation, or async scheduling.
- Add reporter tests and guardrail tests equivalent to Android, including GA4 naming, param count including common params, reserved prefixes, privacy fields, and reporter output.

## User Identity And Properties

`user_id` is GA4 User-ID only. Set it through the tracker/adapter after login and clear it on logout, account switch, auth invalidation, or Delete Account completion. Do not register it as a custom dimension and do not send it as an event parameter.

User properties such as `sign_in_type`, `has_bound_device`, `subscription_tier`, and `main_language` must be stable segmentation fields and must be set/cleared through tracker/adapter APIs.

Do not collect email, phone number, nickname, chat content, note content, transcript text, reminder text, file names, attachment names, precise location, device serial number, tokens, secrets, raw errors, request ids, response bodies, or stack traces.

## Workflow

1. Read the requirement document and identify meaningful business moments.
2. Add or update `analytics_schema/<module>.yaml` first, using schema v2.
3. Update `docs/tracking-plan.md` with the same event names, triggers, params, privacy notes, report usage, and Android/iOS verification.
4. Run `ruby tools/validate_analytics_schema.rb` and fix schema errors before App implementation.
5. Check GA4 naming, param count, reserved prefixes, custom definitions/metrics, and privacy constraints.
6. Identify minimal insertion points and preserve existing business behavior before adding reporter calls.
7. Implement Android from the approved contract: add/update `AnalyticsEventName`, `AnalyticsEventSpec`, typed enums, module reporter, and contract/reporter tests.
8. Implement iOS from the same contract through the iOS analytics facade and provider adapter.
9. Run touched feature tests plus analytics tests, then verify with DebugView and Realtime/Reports/Explore/Looker Studio/BigQuery as needed.
10. Register only custom dimensions and metrics required for recurring analysis, funnels, dashboards, QA, or exports.

## Review Checklist

- Event exists in schema and Tracking Plan with goal, trigger, properties, privacy notes, and verification.
- App code does not embed long-form governance spec text; schema, Tracking Plan, privacy notes, dashboards, and verification checklists stay in the governance repo.
- Active YAML uses `schema_version: 2` and has `implementation_contract`.
- `ruby tools/validate_analytics_schema.rb` passes before Android/iOS code generation.
- Android `AnalyticsEventName.value` matches active YAML `events[].event_name`.
- Event and param names follow GA4 limits and avoid reserved prefixes/names.
- Common params are injected by tracker/adapter and not duplicated by business code.
- Params are non-sensitive, low-cardinality, max 25 per event including common params.
- Failure branches use typed `failure_reason` where analysis needs it.
- Duration analysis uses terminal-event metrics such as `*_duration_ms` when needed.
- Instrumentation preserves existing business logic, return values, state transitions, navigation, error handling, retries, and async timing.
- Analytics failures cannot block, crash, retry, navigate, or change user-visible behavior.
- Android feature code does not import Firebase Analytics directly.
- iOS feature code goes through its analytics facade and does not call Firebase Analytics directly.
- Android and iOS use the same event names, trigger boundaries, required params, optional params, enum values, and privacy notes.
- Dashboards and GA4 reports can split by `platform`, `environment`, and `build_region` without platform-specific event names.

## References

- `analytics_schema/app_basic.yaml`
- `analytics_schema/account.yaml`
- `analytics_schema/tutorial.yaml`
- `analytics_schema/translation.yaml`
- `docs/tracking-plan.md`
- Firebase Analytics Android API: https://firebase.google.com/docs/reference/android/com/google/firebase/analytics/FirebaseAnalytics
- GA4 event naming rules: https://support.google.com/analytics/answer/13316687
- GA4 event collection limits: https://support.google.com/analytics/answer/9267744
- GA4 custom dimensions and metrics: https://support.google.com/analytics/answer/14240153
