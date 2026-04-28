# Analytics Tracking Plan

This document is the human-readable source for event ownership, purpose, and verification. Keep it aligned with `analytics_schema/*.yaml`.

## Governance Rules

- Define the event before implementation.
- Prefer typed analytics contracts over direct provider SDK calls.
- Keep Android and iOS aligned on event names, trigger boundaries, required properties, optional properties, enum values, privacy notes, and verification steps.
- Register GA4 custom definitions only for properties used in recurring reports, funnels, retention, path analysis, QA, or exports.
- Never commit provider API keys, project tokens, server URLs, or other credentials.

## Required Event Fields

| Field | Required | Notes |
| --- | --- | --- |
| `event_name` | Yes | Stable lower snake case event name |
| `goal` | Yes | Product, data, or QA reason |
| `owner` | Yes | Product area or module |
| `trigger` | Yes | Exact firing boundary |
| `required_properties` | Yes | Must be present for analysis |
| `optional_properties` | Yes | Useful context |
| `platforms` | Yes | Android, iOS, or Android+iOS |
| `recommended_or_custom` | Yes | GA4 recommended or custom |
| `key_event` | Yes | Whether GA4 marks it as conversion/key event |
| `privacy_notes` | Yes | PII and cardinality review |
| `verification` | Yes | DebugView, Realtime, report, export, or QA steps |

## Current Production Slice

The first production slice focuses on app startup:

| Event | Owner | Platforms | Trigger |
| --- | --- | --- | --- |
| `app_boot_started` | app | Android+iOS | Cold-start initialization begins after analytics can safely emit |
| `app_boot_completed` | app | Android+iOS | Base initialization completes and the app can enter a usable state |
| `app_boot_degraded` | app | Android+iOS | Non-fatal startup failure occurs but app continues |

Schema: `analytics_schema/app_boot.yaml`

## POC Reference Events

The provider POCs used this shared manual event set for comparability:

- `app_boot_completed`
- `login_completed`
- `device_binding_completed`
- `voice_chat_completed`
- `media_import_completed`
- `note_import_completed`
- `reminder_alert_triggered`

These events are useful for provider evaluation. Before using them as production events, promote each event into `analytics_schema/*.yaml` with full Tracking Plan fields.

## Prefix Taxonomy

| Prefix | Owner |
| --- | --- |
| `app_` | App shell, lifecycle, startup, foreground/background |
| `device_` | Glasses lifecycle, BLE, binding, connection, firmware |
| `account_` | Login, signup, profile, account state |
| `chat_` | Voice chat, text chat, AI response lifecycle |
| `media_` | Gallery, capture, import, sync |
| `note_` | Notes import, creation, detail usage |
| `reminder_` | Reminder creation, alert, completion |

Existing canonical event names should not be renamed only for prefix consistency. Rename or migrate events through an explicit Tracking Plan change.

## Privacy Guardrails

Do not collect:

- Email, phone, nickname, or chat identifiers.
- Chat content, note content, transcript text, reminder text, file names, or attachment names.
- Precise location, device serial number, tokens, secrets, raw URLs, stack traces, or raw exception messages.
- High-cardinality free text values.

Prefer low-cardinality enums, booleans, counts, durations, and coarse buckets.
