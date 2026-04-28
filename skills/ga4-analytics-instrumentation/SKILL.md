---
name: ga4-analytics-instrumentation
description: Use when adding, changing, reviewing, or validating GA4/Firebase Analytics events, event parameters, user properties, dashboards, exports, or Android/iOS analytics instrumentation.
---

# GA4 Analytics Instrumentation

## Overview

The Tracking Plan and analytics schema are the source of truth for event semantics. GA4/Firebase limits are hard gates, but event names, trigger timing, properties, privacy notes, and verification criteria must be approved before production code is written.

Business code must call a typed analytics contract and tracker. Keep Firebase SDK usage behind an app/infrastructure adapter so Android and iOS can share event semantics and later route to other providers.

## Source Of Truth

Before changing a formal event, check:

- `analytics_schema/*.yaml` for machine-readable event contracts.
- `docs/tracking-plan.md` for human-readable ownership, purpose, and verification notes.
- The active product Tracking Plan if it lives in Feishu or another planning system.

If sources disagree, do not silently rename or reinterpret events in code. Update the Tracking Plan or propose a migration first.

The canonical P0 events from the current POC remain useful reference events:

- `app_boot_completed`
- `login_completed`
- `device_binding_completed`
- `voice_chat_completed`
- `media_import_completed`
- `note_import_completed`
- `reminder_alert_triggered`

For production app startup, prefer:

- `app_boot_started`
- `app_boot_completed`
- `app_boot_degraded`

Do not rename existing canonical events only to satisfy a new prefix taxonomy. Prefix migration must be an explicit Tracking Plan change.

## Tracking Plan Gate

Every new or changed production event needs these fields before implementation:

| Field | Meaning |
| --- | --- |
| `event_name` | Stable GA4 event name |
| `goal` | Why product, data, or QA needs the event |
| `owner` | Product area or module responsible for the event |
| `trigger` | Exact firing moment, including success/failure boundary |
| `required_properties` | Properties required for analysis and QA |
| `optional_properties` | Useful context that is not mandatory |
| `platforms` | Android, iOS, or Android+iOS |
| `recommended_or_custom` | GA4 recommended event or custom event |
| `key_event` | Whether GA4 should mark it as a key event/conversion |
| `privacy_notes` | PII, sensitive data, and high-cardinality review |
| `verification` | DebugView, Realtime, report, BigQuery, or QA steps |

An event without these fields is a draft. Do not implement it as a formal production event.

For dual-platform events, `platforms` must explicitly say `Android+iOS`. The contract must describe platform-specific trigger notes when Android and iOS lifecycle callbacks differ.

## GA4 Hard Rules

| Item | GA4/Firebase rule | Project rule |
| --- | --- | --- |
| Event name | Case-sensitive, max 40 chars, starts with a letter, letters/numbers/underscores only | Lower snake case; approved canonical name or ownership prefix |
| Event params | Max 25 params per event | Keep params low-cardinality and analysis-ready |
| Param name | Max 40 chars | Lower snake case, starts with a letter, no leading underscore |
| String param value | Usually max 100 chars | Prefer enums, booleans, counts, durations, coarse buckets |
| User property | Name max 24 chars, value max 36 chars | Stable segmentation fields only |
| Custom definitions | Limited dimensions and metrics | Register only params used in reports, funnels, retention, QA, or exports |

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

If two prefixes seem plausible, choose the system that produces the event. Binding a pair of glasses is `device_binding_completed`, not `app_binding_completed`.

## Properties And Privacy

Feature modules should not hand-build common technical metadata. The tracker or adapter may inject:

- `platform`
- `environment`
- `build_region`
- `build_type`
- `app_version_name`
- `app_version_code`

Shared analysis params should use typed enums where possible:

- `entry_point`
- `surface`
- `trigger_source`
- `failure_reason`

Recommended `failure_reason` values:

- `network_error`
- `permission_denied`
- `validation_failed`
- `timeout`
- `unsupported_state`
- `sdk_error`

Do not collect email, phone number, nickname, chat content, note content, transcript text, reminder text, file names, attachment names, precise location, device serial number, tokens, secrets, or other PII.

`user_id` is allowed only as a stable internal non-PII identifier for GA4 User-ID behavior. Set it after login and clear it on logout or auth invalidation. Do not register it as a custom user property.

## Cross-Platform Contract

Treat Android and iOS analytics as implementations of one shared tracking contract, not separate event inventories.

Each schema entry should include:

- `event_name`
- `owner`
- `platforms`
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

For app startup, both platforms use:

- `app_boot_started`
- `app_boot_completed`
- `app_boot_degraded`

Shared startup boundaries:

| Event | Boundary |
| --- | --- |
| `app_boot_started` | Cold-start initialization begins after analytics can safely emit |
| `app_boot_completed` | Base initialization completes and the user can enter a usable state |
| `app_boot_degraded` | A non-blocking initialization failure occurs, but the app continues |

Both platforms should expose a typed facade and keep Firebase SDK usage behind an adapter:

```text
AnalyticsTracker
AnalyticsEvent
AnalyticsParam
Ga4AnalyticsAdapter
```

Business code should call `analytics.track(...)`. It should not call Android `FirebaseAnalytics.logEvent(...)` or iOS `Analytics.logEvent(...)` directly.

Do not let enum values drift by platform. If Android emits `network_error`, iOS must not emit `network_unavailable` for the same semantic failure unless the Tracking Plan explicitly defines both values.

## Workflow

1. Read `analytics_schema/*.yaml`, `docs/tracking-plan.md`, and the current product Tracking Plan.
2. If required Tracking Plan fields are missing, update the plan or ask for approval before implementation.
3. Check whether GA4 has a recommended event that truly matches the semantics.
4. Choose the canonical event name: existing approved name first; otherwise approved ownership-prefixed name.
5. For dual-platform work, confirm Android and iOS trigger timing, required params, optional params, and enum values before code.
6. Add or update the typed analytics contract in the shared/domain/API layer.
7. Write or update contract tests first. Cover GA4 length limits, naming pattern, reserved prefixes/names, param count, and privacy guardrails.
8. Implement reporting through the analytics tracker only. Feature code must not import Firebase Analytics directly.
9. Register GA4 custom definitions only for params used by funnels, retention, path analysis, dashboards, exports, or recurring QA.
10. Verify with DebugView first, then Realtime or a non-debug session. For reports or exports, verify in GA4 Explorations, Reports, Looker Studio, or BigQuery.
11. Verify Android and iOS side by side. GA4 should merge both platforms under the same event name, and `platform` should split them cleanly.

## Review Checklist

- Event exists in the Tracking Plan with goal, trigger, properties, privacy notes, and verification steps.
- Event name follows GA4 limits, is stable, is not value-derived, and is not reserved.
- Existing canonical events were not renamed just to satisfy prefix preferences.
- Params are non-sensitive, low-cardinality, max 25 per event, and string values stay within GA4 limits.
- Failure branches include typed `failure_reason` where analysis needs it.
- User properties are stable segmentation fields and fit GA4 limits.
- Custom definitions are registered only for properties needed in reports or analysis.
- Contract tests cover GA4 naming, reserved names, prefix policy, param limits, and privacy rules.
- Android feature code does not import Firebase Analytics directly.
- iOS feature code goes through its analytics facade and does not call Firebase Analytics directly.
- Android and iOS use the same event names, trigger boundaries, required params, optional params, enum values, and privacy notes.
- Dashboards and GA4 reports can be split by `platform` without platform-specific event names.

## References

- `analytics_schema/app_boot.yaml`
- `docs/tracking-plan.md`
- Firebase Analytics Android API: https://firebase.google.com/docs/reference/android/com/google/firebase/analytics/FirebaseAnalytics
- GA4 event naming rules: https://support.google.com/analytics/answer/13316687
- GA4 event collection limits: https://support.google.com/analytics/answer/9267744
- GA4 custom dimensions and metrics: https://support.google.com/analytics/answer/14240153
