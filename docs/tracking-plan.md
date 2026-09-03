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


## Current Implementation Architecture

- Android typed contract lives in `domain:api:analytics`: `AnalyticsEvent`, `AnalyticsEventName`, `AnalyticsParamName`, `AnalyticsParamValue`, `AnalyticsEventSpec`, typed enums, and module reporters.
- Android app infrastructure provides `AnalyticsTracker`, `DefaultAnalyticsTracker`, `AnalyticsAdapter`, `Ga4AnalyticsAdapter`, and `AnalyticsCommonParamProvider`.
- Business, feature, domain, and data code must call module reporters or `AnalyticsTracker`; they must not call `FirebaseAnalytics` directly.
- Common params are injected by the tracker/adapter layer: `platform`, `environment`, `build_region`, `build_type`, `app_version_name`, `app_version_code`.
- Current Android `build_region` rule is `BuildConfig.IS_PRODUCT=true -> us`; non-product builds report `sg`.
- iOS must expose an equivalent facade/adapter boundary and use the same event names, params, enum values, and privacy rules.

## YAML Protocol Version 2

- Active schemas use `schema_version: 2` and include `common_properties`, `implementation_contract`, and `events`.
- Every event keeps the approved semantic fields: event name, goal, Android/iOS trigger, required/optional properties, allowed values, privacy notes, GA4 custom definitions, dashboard usage, and Android/iOS verification.
- Add `ga4_custom_metrics` only when an event sends a numeric parameter intended for GA4 custom metric registration.
- Schema and Tracking Plan must be updated before App code. If implementation finds a conflict, update the contract instead of silently changing code semantics.

## Duration And Event Pairing

GA4 does not automatically pair two custom events and calculate elapsed time in the standard UI. When a module needs duration analysis, report a low-risk numeric metric on the terminal event, such as `*_duration_ms`, and register it as a GA4 custom metric. Use correlation ids only for BigQuery/debug analysis, keep them non-PII, and do not register high-cardinality ids as GA4 custom dimensions.

## Minimal App Analytics Production Slice

The minimal App analytics slice was the first formal end-to-end GA4 implementation scope. It now remains focused on startup and app-health reporting.

Startup events are defined in `analytics_schema/app_basic.yaml`. The earlier `app_login_started`, `app_login_completed`, and `app_login_failed` names were approved for the first App-health slice, but account login is now migrated to `account_login_started`, `account_login_completed`, and `account_login_failed` in `analytics_schema/account.yaml`. After migration, the same login or auth-restore behavior must not emit both old `app_login_*` and new `account_login_*` events.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `app_boot_started` | app | Android+iOS | Cold-start initialization begins after analytics can safely emit | Common adapter params only |
| `app_boot_completed` | app | Android+iOS | Base initialization completes and the app can enter a usable state | Common adapter params only |
| `app_boot_degraded` | app | Android+iOS | Non-fatal startup failure occurs but app continues | `failure_reason`, `degraded_component` |

### Minimal App Naming Note

The prefix taxonomy reserves `account_` for login, signup, profile, and account-state events. `app_login_*` is a deprecated App-level first-slice exception and is superseded by the Account Production Slice. Do not implement dual emission for the same controlled login behavior.

### Minimal App Report Usage

- Startup completion funnel: `app_boot_started` -> `app_boot_completed`.
- Account-usable state funnel after migration: `app_boot_completed` -> `account_login_completed`.
- Login completion funnel after migration: `account_login_started` -> `account_login_completed`.
- Startup degradation table or donut: `app_boot_degraded` by `failure_reason` and `degraded_component`.
- Login failure table or donut after migration: `account_login_failed` by `sign_in_type`, `failure_reason`, `entry_point`, and `surface`.
- Saved GA4 report assets should use the `App Boot` or `Account` prefix so they are easy to find in Reports Library.

## App Basic Production Slice

The App Basic slice covers App shell behavior: startup, formal explanation links, version notices, and language fallback. All events below are defined in `analytics_schema/app_basic.yaml`.

`legal_link_*`, `version_notice_viewed`, and `language_fallback_*` are deprecated unprefixed Basic Function names. The canonical App Basic names are `app_legal_link_*`, `app_version_notice_viewed`, and `app_language_fallback_*`. Android and iOS must not emit both old and new names for the same behavior.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `app_boot_started` | app | Android+iOS | Cold-start initialization begins after analytics can safely emit | Common adapter params only |
| `app_boot_completed` | app | Android+iOS | Base initialization completes and the app can enter a usable state | Common adapter params only |
| `app_boot_degraded` | app | Android+iOS | Non-fatal startup failure occurs but app continues | `failure_reason`, `degraded_component` |
| `app_legal_link_opened` | app | Android+iOS | User taps a formal help, terms, privacy, or instruction link and the open action is accepted | `entry_point`, `surface` |
| `app_legal_link_open_failed` | app | Android+iOS | A formal explanation link open attempt fails and the user remains in the current context | `failure_reason`, `surface` |
| `app_version_notice_viewed` | app | Android+iOS | A normal version notice matches and is shown as a dialog or page | `entry_point`, `surface` |
| `app_language_fallback_applied` | app | Android+iOS | Main language or Notes language has no exact match and successfully falls back to an available result | `surface`, `trigger_source` |
| `app_language_fallback_blocked` | app | Android+iOS | Language selection or fallback cannot produce an available result and stays in a failure state | `failure_reason`, `surface` |

### App Basic GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `failure_reason` | P0 | Build failure breakdowns for startup degradation, legal link failures, and language fallback blocks |
| `degraded_component` | P0 | Identify which startup component degraded |
| `surface` | P0 | Split app shell behavior by application, splash, login, settings, chat, home, and Notes surfaces |
| `entry_point` | P1 | Compare where users enter startup, legal links, version notices, and language fallback paths |
| `trigger_source` | P1 | Distinguish user, system, push, deep link, server-push, or scheduler-triggered basic behavior |

Do not register or upload full URLs, browser error details, version notice body text, raw language candidate lists, raw locale strings, tokens, log paths, raw exception messages, or stack traces.

### App Basic Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Cold start the app and confirm `app_boot_started` appears before `app_boot_completed`.
- Confirm `app_boot_completed` can be split by `platform`, `environment`, and `build_region`.
- Simulate a controlled non-fatal startup degradation and confirm `app_boot_degraded` appears with approved `failure_reason` and `degraded_component`.
- Tap one formal help, terms, privacy, or instruction link and confirm `app_legal_link_opened` appears once.
- Simulate invalid link or unavailable browser and confirm `app_legal_link_open_failed` appears with an approved `failure_reason`.
- Use an unread version notice state and confirm `app_version_notice_viewed` appears once when the notice is shown.
- Simulate no-exact-match language fallback and confirm `app_language_fallback_applied` appears with approved `surface` and `trigger_source`.
- Simulate no available language result and confirm `app_language_fallback_blocked` appears with an approved `failure_reason`.
- Confirm all events route through the Android analytics tracker/adapter and no event contains full URL, token, notice body, language candidate list, raw error, or stack trace.

### App Basic iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Cold start the app and confirm `app_boot_started` appears before `app_boot_completed`.
- Confirm `app_boot_completed` can be split by `platform`, `environment`, and `build_region`.
- Simulate a controlled non-fatal startup degradation and confirm `app_boot_degraded` appears with approved `failure_reason` and `degraded_component`.
- Tap one formal help, terms, privacy, or instruction link and confirm `app_legal_link_opened` appears once.
- Simulate invalid link or unavailable browser and confirm `app_legal_link_open_failed` appears with an approved `failure_reason`.
- Use an unread version notice state and confirm `app_version_notice_viewed` appears once when the notice is shown.
- Simulate no-exact-match language fallback and confirm `app_language_fallback_applied` appears with approved `surface` and `trigger_source`.
- Simulate no available language result and confirm `app_language_fallback_blocked` appears with an approved `failure_reason`.
- Confirm all events route through the iOS analytics facade/adapter and no event contains full URL, token, notice body, language candidate list, raw error, or stack trace.

## App Support Production Slice

The App Support slice covers the formal Settings > Contact us support flow. All events below are defined in `analytics_schema/app_support.yaml`.

`contact_us_*` is an approved canonical event family from the existing Tracking Plan. It remains unchanged as a support-flow naming exception and should not be renamed to an `app_` prefix only for prefix consistency.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `contact_us_started` | app | Android+iOS | User taps Contact us and the support request or pre-upload flow starts | `entry_point`, `surface` |
| `contact_us_opened` | app | Android+iOS | No unread support reply exists and the Intercom composer opens successfully | `entry_point`, `surface` |
| `contact_us_reply_opened` | app | Android+iOS | User taps Contact us from an unread reply indicator and Intercom Messenger opens successfully | `entry_point`, `surface` |
| `contact_us_failed` | app | Android+iOS | Support chat window fails before opening because of network, permission, authorization, configuration, or SDK failure | `failure_reason`, `entry_point`, `surface` |

### App Support GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS support flow behavior |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `entry_point` | P0 | Split Contact us entry source such as settings or notification |
| `surface` | P0 | Distinguish settings and support surfaces |
| `trigger_source` | P1 | Distinguish user-triggered and system-triggered support flow attempts |
| `failure_reason` | P0 | Build Contact us failure breakdowns |

Do not register or upload `userid`, Intercom conversation id, report contents, attachment names, chat contents, log contents, raw errors, or stack traces.

### App Support Report Usage

- Contact us funnel: `contact_us_started` -> `contact_us_opened` or `contact_us_reply_opened`.
- Contact us failure table or donut: `contact_us_failed` by `failure_reason`, `entry_point`, and `surface`.
- Unread reply entry report: `contact_us_reply_opened` by `platform`, `environment`, and `build_region`.

### App Support Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Tap Contact us from Settings and confirm `contact_us_started` appears once.
- Open Contact us with no unread reply and confirm `contact_us_opened`.
- Open Contact us from an unread reply indicator and confirm `contact_us_reply_opened`.
- Simulate network failure, missing configuration, authorization failure, or SDK open failure and confirm `contact_us_failed` with an approved `failure_reason`.
- Confirm all events route through the Android analytics tracker/adapter and no event contains user ID, conversation ID, chat content, attachment name, report content, raw error, or log content.

### App Support iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Tap Contact us from Settings and confirm `contact_us_started` appears once.
- Open Contact us with no unread reply and confirm `contact_us_opened`.
- Open Contact us from an unread reply indicator and confirm `contact_us_reply_opened`.
- Simulate network failure, missing configuration, authorization failure, or SDK open failure and confirm `contact_us_failed` with an approved `failure_reason`.
- Confirm the iOS analytics facade emits the same event names, params, enum values, and privacy boundaries as Android.
- Confirm GA4 can split the shared events by `platform` without platform-specific event names.

## Account Production Slice

The Account slice covers formal account login, auth-state restoration, account settings, high-risk data controls, username rule validation, logout, and auth invalidation. All events below are defined in `analytics_schema/account.yaml`.

This slice owns the formal login contract. The earlier `app_login_*` login events have been merged into `account_login_*` and `analytics_schema/app_login.yaml` has been removed. `account_login_*` is the canonical login and account-usable-state contract for future Android and iOS implementation. The same login, session-restore, or auth-restore behavior must not emit both `app_login_*` and `account_login_*`.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `account_login_started` | account | Android+iOS | User submits email-code login, starts Google or Apple login, or the app starts session/auth-state restoration | `sign_in_type`, `entry_point`, `surface`, `trigger_source` |
| `account_login_completed` | account | Android+iOS | Login or auth-state restoration succeeds and the app can enter account-usable state | `sign_in_type`, `entry_point`, `surface` |
| `account_login_failed` | account | Android+iOS | Login or auth-state restoration ends in a failure or formal blocked state | `sign_in_type`, `failure_reason`, `entry_point`, `surface` |
| `account_settings_viewed` | account | Android+iOS | User opens account information or Data Controls from Settings or another approved account entry point | `entry_point`, `surface` |
| `account_data_control_submitted` | account | Android+iOS | User confirms Export Data, Delete Data, or Delete Account and the request is submitted | `action_type`, `surface`, `trigger_source` |
| `account_data_control_completed` | account | Android+iOS | The app receives success or accepted status for Export Data, Delete Data, or Delete Account and shows a user-visible success state | `action_type`, `surface` |
| `account_data_control_failed` | account | Android+iOS | Export Data, Delete Data, or Delete Account fails or is formally blocked before success or accepted state | `action_type`, `failure_reason`, `surface` |
| `account_username_rule_evaluated` | account | Android+iOS | User submits a username or display name from login completion or account settings and formal validation runs | `surface`, `trigger_source` |
| `account_username_rule_blocked` | account | Android+iOS | Username or display-name submission is blocked by a formal validation rule | `rule_type`, `failure_reason`, `surface` |
| `account_logout_completed` | account | Android+iOS | User confirms logout and the app completes local account cleanup | `entry_point`, `surface`, `trigger_source` |
| `account_auth_state_invalidated` | account | Android+iOS | Token, session, or account authorization becomes invalid outside user-initiated logout and the app clears local account state | `failure_reason`, `entry_point`, `surface`, `trigger_source` |

### Account GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS account behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `sign_in_type` | P0 | Split login funnel by email, Google, Apple, or unknown sign-in type |
| `failure_reason` | P0 | Build login, data-control, username-rule, and auth-invalidation failure breakdowns |
| `action_type` | P0 | Split Export Data, Delete Data, and Delete Account flows |
| `rule_type` | P1 | Identify username or display-name validation blockers without collecting submitted text |
| `surface` | P0 | Split account behavior by application, login, settings, home, account, or unknown surface |
| `entry_point` | P1 | Compare where users enter login, account settings, data control, logout, or auth recovery |
| `trigger_source` | P1 | Distinguish user, system, session-restore, token-refresh, or server-triggered account behavior |

Recommended user-scoped custom dimensions remain the shared account properties:

| User Property | Reason |
| --- | --- |
| `sign_in_type` | Segment signed-in users by current login method |
| `has_bound_device` | Compare account behavior by binding state |
| `subscription_tier` | Compare account behavior by membership tier |
| `main_language` | Compare account behavior by effective main language |

`user_id` is only GA4 User-ID. Do not register it as a custom dimension and do not send it as an event parameter. It must be a stable internal non-PII identifier set after login and cleared on logout, auth invalidation, account switch, or Delete Account completion.

Do not register or upload email, phone, nickname, verification code, provider account id, auth token, refresh token, submitted username, account contents, request ids, response bodies, raw SDK payloads, raw errors, or stack traces.

### Account Report Usage

- Login funnel: `account_login_started` -> `account_login_completed` or `account_login_failed`.
- Account usable-state funnel: `app_boot_completed` -> `account_login_completed`.
- Login failure table or donut: `account_login_failed` by `sign_in_type`, `failure_reason`, `entry_point`, and `surface`.
- Data-control funnel: `account_data_control_submitted` -> `account_data_control_completed` or `account_data_control_failed`.
- Username-rule blockers: `account_username_rule_blocked` by `rule_type`, `failure_reason`, `surface`, and `platform`.
- Identity cleanup audit: `account_logout_completed` and `account_auth_state_invalidated`, with QA evidence that GA4 User-ID and account user properties are cleared.

### Account Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Trigger email, Google, Apple, and session-restore login paths and confirm `account_login_started` appears before `account_login_completed`.
- Simulate validation, authorization, timeout, SDK, and network failures and confirm only `account_login_failed` appears with approved enum values.
- Confirm the same controlled login behavior does not also emit `app_login_started`, `app_login_completed`, or `app_login_failed`.
- Open account settings and confirm `account_settings_viewed`.
- Submit, complete, and fail Export Data, Delete Data, and Delete Account flows and confirm the three `account_data_control_*` events with approved `action_type`.
- Submit valid and invalid username values and confirm `account_username_rule_evaluated` and `account_username_rule_blocked` without submitted text.
- Complete user-initiated logout and confirm `account_logout_completed`; then confirm GA4 User-ID and account user properties are cleared.
- Simulate token or session invalidation outside logout and confirm `account_auth_state_invalidated`; then confirm GA4 User-ID and account user properties are cleared.
- Confirm all account events route through the Android analytics tracker/adapter and no event contains email, phone, nickname, verification code, provider account id, token, request id, response body, raw error, stack trace, submitted username, or account contents.

### Account iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Trigger email, Google, Apple, and session-restore login paths and confirm `account_login_started` appears before `account_login_completed`.
- Simulate validation, authorization, timeout, SDK, and network failures and confirm only `account_login_failed` appears with approved enum values.
- Confirm the same controlled login behavior does not also emit `app_login_started`, `app_login_completed`, or `app_login_failed`.
- Open account settings and confirm `account_settings_viewed`.
- Submit, complete, and fail Export Data, Delete Data, and Delete Account flows and confirm the three `account_data_control_*` events with approved `action_type`.
- Submit valid and invalid username values and confirm `account_username_rule_evaluated` and `account_username_rule_blocked` without submitted text.
- Complete user-initiated logout and confirm `account_logout_completed`; then confirm GA4 User-ID and account user properties are cleared.
- Simulate token or session invalidation outside logout and confirm `account_auth_state_invalidated`; then confirm GA4 User-ID and account user properties are cleared.
- Confirm all account events route through the iOS analytics facade/adapter and no event contains email, phone, nickname, verification code, provider account id, token, request id, response body, raw error, stack trace, submitted username, or account contents.
- Confirm GA4 Reports, Realtime, and Explore can split the shared account events by `platform=android` and `platform=ios` without platform-specific event names.

## Device Production Slice

The Device slice covers the formal device entry, connection and binding, device settings, device info sync, auto-reconnect, version gate, and OTA firmware upgrade flows. All events below are defined in `analytics_schema/device.yaml`.

Eight events in this slice use the `device_` prefix for reconnect, version gate, and OTA families to align with the prefix taxonomy. This is the canonical naming for these event families.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `device_hub_viewed` | device | Android+iOS | Home, Settings, or detail page renders the formal device entry and status card | `entry_point`, `surface` |
| `device_primary_action_tapped` | device | Android+iOS | User taps the primary action on the device card to connect, reconnect, view details, or enter upgrade entry | `surface`, `trigger_source` |
| `device_entry_blocked` | device | Android+iOS | Device entry is blocked by no bound device, forced upgrade gate, or formal permission barrier | `failure_reason`, `surface` |
| `device_binding_started` | device | Android+iOS | User enters the formal device binding flow from an approved entry point | `entry_point`, `trigger_source`, `surface` |
| `device_binding_completed` | device | Android+iOS | Pairing succeeds and a formal binding result is formed; set `has_bound_device=true` | `surface`, `trigger_source` |
| `device_binding_failed` | device | Android+iOS | The binding flow ends in a failure or timeout state | `failure_reason`, `surface` |
| `device_settings_viewed` | device | Android+iOS | User enters the bound device detail or settings page | `entry_point`, `surface` |
| `device_setting_updated` | device | Android+iOS | User completes a formal device setting update, calibration, unbind, or reset | `surface`, `trigger_source` |
| `device_setting_update_failed` | device | Android+iOS | A formal setting update is blocked or fails before completing | `failure_reason`, `surface` |
| `device_sync_evaluated` | device | Android+iOS | The formal sync chain begins evaluating device name, firmware version, connection state, or unbind cleanup | `surface`, `trigger_source` |
| `device_sync_completed` | device | Android+iOS | The formal sync chain produces a visible completion result | `surface`, `trigger_source` |
| `device_sync_failed` | device | Android+iOS | The formal sync chain fails or compensation does not complete | `failure_reason`, `surface` |
| `device_reconnect_started` | device | Android+iOS | Auto-reconnect or manual reconnect chain begins after disconnection | `entry_point`, `trigger_source`, `surface` |
| `device_reconnect_completed` | device | Android+iOS | Reconnection completes and device returns to usable connected state | `surface`, `trigger_source` |
| `device_reconnect_failed` | device | Android+iOS | Auto-reconnect or manual reconnect ends in a failed state | `failure_reason`, `surface` |
| `device_version_gate_evaluated` | device | Android+iOS | A formal flow enters firmware version evaluation | `surface`, `trigger_source` |
| `device_version_gate_passed` | device | Android+iOS | Version evaluation passes and the requested flow can continue | `surface`, `trigger_source` |
| `device_version_gate_blocked` | device | Android+iOS | A formal flow is intercepted because firmware or app version does not meet requirements | `failure_reason`, `surface` |
| `device_ota_started` | device | Android+iOS | User confirms starting a firmware upgrade or forced upgrade begins | `entry_point`, `trigger_source`, `surface` |
| `device_ota_completed` | device | Android+iOS | Firmware upgrade completes and device enters post-upgrade result state | `surface`, `trigger_source` |
| `device_ota_failed` | device | Android+iOS | OTA ends in a failure state due to interruption, timeout, or verification failure | `failure_reason`, `surface` |

### Device GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS device behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `failure_reason` | P0 | Build failure breakdowns for binding, reconnect, OTA, version gate, and setting update failures |
| `surface` | P0 | Split device behavior by home, settings, device, onboarding, and background surfaces |
| `entry_point` | P1 | Compare where users enter binding, settings, reconnect, and OTA flows |
| `trigger_source` | P1 | Distinguish user, system, and device-triggered behaviors |
| `binding_mode` | P1 | Distinguish first-time binding from rebind |
| `setting_type` | P1 | Identify which device settings are most changed or most fail |
| `upgrade_mode` | P1 | Distinguish user-initiated OTA from forced upgrade gate OTA |

Do not register device name text, device address, BLE raw event data, firmware version string, pairing code, device serial number, stack traces, or raw error codes.

### Device Allowed Values

Device-specific enum values (see `analytics_schema/device.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `binding_mode` | `first_time`, `rebind`, `unknown` |
| `action_type` (device card) | `connect`, `reconnect`, `view_details`, `upgrade`, `unknown` |
| `setting_type` | `rename`, `unbind`, `reset`, `restart`, `calibrate`, `kws_toggle`, `video_length`, `unknown` |
| `sync_type` | `name`, `version`, `connection_state`, `unbind_cleanup`, `unknown` |
| `reconnect_mode` | `auto`, `manual`, `unknown` |
| `upgrade_mode` | `user_initiated`, `forced`, `unknown` |

`entry_point`, `surface`, `trigger_source`, and `failure_reason` follow the shared enum values defined per event in `analytics_schema/device.yaml`. Do not extend these values without a Tracking Plan update.

### Device User Property Notes

`has_bound_device` is a shared account user property. The device module is responsible for keeping it accurate:

- Set `has_bound_device=true` after `device_binding_completed`.
- Set `has_bound_device=false` after `device_setting_updated` with `setting_type=unbind` completes successfully.
- The value is cleared on logout and auth invalidation via the account module.

### Device Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Navigate to Home and Settings device entry and confirm `device_hub_viewed` appears once per surface with `platform=android`.
- Tap each primary device card action and confirm `device_primary_action_tapped` with the correct `action_type`.
- Simulate no-device and forced-upgrade gate states and confirm `device_entry_blocked` with approved `failure_reason`.
- Start a first-time and a rebind binding flow and confirm `device_binding_started` with the correct `binding_mode`.
- Complete a binding and confirm `device_binding_completed`; then confirm `has_bound_device=true` is set as a user property.
- Simulate timeout, permission denial, and pairing failure and confirm `device_binding_failed` with approved `failure_reason`.
- Open the device detail page and confirm `device_settings_viewed`.
- Trigger each `setting_type` (rename, unbind, reset, restart, calibrate, kws_toggle, video_length) and confirm `device_setting_updated`.
- Simulate device disconnect or network failure during a setting update and confirm `device_setting_update_failed` with an approved `failure_reason`; after unbind confirm `has_bound_device=false`.
- Trigger a version sync and confirm `device_sync_evaluated` and `device_sync_completed` with `sync_type=version`.
- Simulate a server write failure during sync and confirm `device_sync_failed` with an approved `failure_reason`.
- Simulate disconnect and allow auto-reconnect to succeed; confirm `device_reconnect_started` with `reconnect_mode=auto` and `device_reconnect_completed`.
- Manually trigger reconnect from Home; confirm `device_reconnect_started` with `reconnect_mode=manual`.
- Simulate reconnect timeout or cancellation; confirm `device_reconnect_failed` with an approved `failure_reason`.
- Enter a binding or usage flow that triggers version checking; confirm `device_version_gate_evaluated`.
- Let the same flow pass compatibility; confirm `device_version_gate_passed` appears and does not include firmware version detail.
- Simulate forced firmware upgrade gate; confirm `device_version_gate_blocked` with `failure_reason=unsupported_state`.
- Start a user-initiated OTA and confirm `device_ota_started` with `upgrade_mode=user_initiated`.
- Complete an OTA and confirm `device_ota_completed`.
- Simulate OTA interruption or timeout; confirm `device_ota_failed` with an approved `failure_reason`.
- Confirm all device events route through the Android analytics tracker/adapter and no event contains device name text, device address, BLE address, firmware version string, pairing code, device serial number, raw BLE error, or stack trace.

### Device iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same event set as Android: `device_hub_viewed`, `device_primary_action_tapped`, `device_entry_blocked`, `device_binding_started`, `device_binding_completed`, `device_binding_failed`, `device_settings_viewed`, `device_setting_updated`, `device_setting_update_failed`, `device_sync_evaluated`, `device_sync_completed`, `device_sync_failed`, `device_reconnect_started`, `device_reconnect_completed`, `device_reconnect_failed`, `device_version_gate_evaluated`, `device_version_gate_passed`, `device_version_gate_blocked`, `device_ota_started`, `device_ota_completed`, `device_ota_failed`.
- Confirm all events use the same event names, required properties, optional properties, and enum values as Android.
- Confirm GA4 can split the shared device events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm all device events route through the iOS analytics facade/adapter and no event contains device name text, device address, firmware version string, pairing code, device serial number, raw BLE error, or stack trace.

### Device Report Usage

- Binding funnel: `device_binding_started` → `device_binding_completed` or `device_binding_failed`.
- Binding failure table: `device_binding_failed` by `failure_reason`, `binding_mode`, and `platform`.
- Reconnect funnel: `device_reconnect_started` → `device_reconnect_completed` or `device_reconnect_failed` by `reconnect_mode`.
- OTA funnel: `device_ota_started` → `device_ota_completed` or `device_ota_failed` by `upgrade_mode`.
- Version gate pass/block volume: `device_version_gate_passed` and `device_version_gate_blocked` by `surface` and `platform`.
- Setting type distribution: `device_setting_updated` by `setting_type` and `platform`.

## Device Usage Production Slice

The Device Usage slice covers coarse glasses usage telemetry emitted by the typed Android `DeviceUsageAnalyticsReporter` and the equivalent future iOS facade. These events remain in `analytics_schema/device.yaml` under the `device` owner; do not create a separate `device_usage.yaml` because the ownership prefix is still `device_`.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `device_usage_wear_session_started` | device | Android+iOS | Wearing state enters an active wear session | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_wear_session_ended` | device | Android+iOS | Active wear session ends | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_bt_connected` | device | Android+iOS | BT audio/profile usable connection enters connected | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_bt_disconnected` | device | Android+iOS | Active BT session leaves connected state | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_ble_connected` | device | Android+iOS | BLE control channel enters connected | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_ble_disconnected` | device | Android+iOS | Active BLE session leaves connected state | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_photo_capture_succeeded` | device | Android+iOS | Device-side photo capture succeeds | `local_date`, `local_hour`, `day_of_week`, `is_weekend` |
| `device_usage_photo_capture_failed` | device | Android+iOS | Device-side photo capture fails or is unsupported | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `failure_reason` |
| `device_usage_video_record_started` | device | Android+iOS | Device-side video recording starts | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_video_record_ended` | device | Android+iOS | Active video recording ends successfully | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_video_record_failed` | device | Android+iOS | Video recording fails before or during a session | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `failure_reason` |
| `device_usage_audio_record_started` | device | Android+iOS | Device-side audio recording starts | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_audio_record_ended` | device | Android+iOS | Active audio recording ends successfully | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_audio_record_failed` | device | Android+iOS | Audio recording fails before or during a session | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `failure_reason` |
| `device_usage_ai_chat_started` | device | Android+iOS | Device-origin AI Chat enters active state | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_ai_chat_ended` | device | Android+iOS | Device-origin AI Chat session ends normally | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_ai_chat_failed` | device | Android+iOS | Device-origin AI Chat fails before or during a session | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `failure_reason` |
| `device_usage_media_playback_started` | device | Android+iOS | Glasses media playback starts | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_media_playback_ended` | device | Android+iOS | Glasses media playback ends | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_call_started` | device | Android+iOS | Phone call audio/session enters active state | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_call_ended` | device | Android+iOS | Active phone call audio/session ends | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_charging_started` | device | Android+iOS | Charging state enters true | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `trigger_source` |
| `device_usage_charging_ended` | device | Android+iOS | Active charging session ends | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `duration_ms`, `duration_bucket` |
| `device_usage_battery_warning_triggered` | device | Android+iOS | Low/critical battery or charger boundary is detected | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `warning_kind` |
| `device_usage_battery_state_sampled` | device | Android+iOS | Rapid battery rise/drop sample passes throttling | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `battery_change_type` |
| `device_usage_media_sync_state_changed` | device | Android+iOS | AP/media-server/import pipeline reaches an approved state boundary | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `sync_state` |
| `device_usage_media_sync_failed` | device | Android+iOS | AP/media-server/import pipeline reports an approved failure boundary | `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `sync_state`, `error_source`, `failure_reason` |

Optional state context shared by Device Usage events: `battery_level`, `is_wearing`, `bt_connected`, `ble_connected`, and `charging`. These are coarse state fields only and must not be used to send raw telemetry streams.

### Device Usage GA4 Custom Definitions And Metrics

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS usage behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `local_date` | P0 | Build local-day usage and retention reports without raw timestamps |
| `local_hour` | P0 | Analyze coarse hourly usage distribution |
| `day_of_week` | P1 | Split weekday/weekend and day-of-week behavior |
| `is_weekend` | P1 | Support simplified weekday/weekend grouping |
| `duration_bucket` | P0 | Analyze session duration distributions without high-cardinality raw durations |
| `failure_reason` | P0 | Build capture, recording, AI Chat, and media sync failure breakdowns |
| `sync_state` | P0 | Analyze media sync pipeline state transitions |
| `error_source` | P0 | Split media sync failures by device, app, network, media server, BT, or ISP |
| `warning_kind` | P1 | Split battery and charger warning boundaries |
| `battery_change_type` | P1 | Split rapid battery drop vs rapid rise samples |
| `voice_source` | P1 | Split device-origin AI Chat source when available |
| `termination_reason` | P1 | Split AI Chat terminal outcomes when available |
| `item_count_bucket` | P1 | Analyze media sync batch size without item-level identifiers |
| `battery_level`, `is_wearing`, `bt_connected`, `ble_connected`, `charging` | P1 | Coarse diagnostic context for device usage and reliability reports |

Recommended custom metric:

| Metric | Priority | Reason |
| --- | --- | --- |
| `duration_ms` | P0 | Numeric duration for terminal session events; use with `duration_bucket` for reporting and QA |

Do not register or upload device name, BLE/MAC address, serial number, raw sensor data, raw battery telemetry stream, charger identifier, raw BT/BLE state dumps, raw command payloads, media file names, thumbnails, media URLs, chat text, prompts, transcripts, audio/video/image content, conversation/message ids, request ids, response bodies, raw errors, stack traces, logs, or precise location.

### Device Usage Allowed Values

| Property | Allowed Values |
| --- | --- |
| `duration_bucket` (state sessions) | `state_01_lt_1m`, `state_02_1m_5m`, `state_03_5m_15m`, `state_04_15m_30m`, `state_05_30m_1h`, `state_06_1h_2h`, `state_07_2h_4h`, `state_08_gte_4h` |
| `duration_bucket` (interaction sessions) | `interaction_01_lt_10s`, `interaction_02_10s_30s`, `interaction_03_30s_1m`, `interaction_04_1m_3m`, `interaction_05_3m_5m`, `interaction_06_5m_10m`, `interaction_07_10m_30m`, `interaction_08_gte_30m` |
| `duration_bucket` (audio sessions) | `audio_01_lt_30s`, `audio_02_30s_1m`, `audio_03_1m_3m`, `audio_04_3m_10m`, `audio_05_10m_30m`, `audio_06_30m_1h`, `audio_07_gte_1h` |
| `sync_state` | `ap_idle`, `ap_started`, `ap_stopped`, `ap_error`, `media_server_idle`, `media_server_started`, `media_server_stopped`, `media_server_error`, `wait_import`, `importing`, `imported`, `unknown` |
| `error_source` | `device`, `app`, `network`, `media_server`, `bt`, `isp`, `unknown` |
| `warning_kind` | `low_battery`, `critical_battery`, `charger_plugged`, `charger_unplugged`, `unknown` |
| `battery_change_type` | `rapid_drop`, `rapid_rise` |
| `item_count_bucket` | `1`, `2_5`, `6_20`, `21_100`, `100_plus`, `unknown` |

`trigger_source`, `voice_source`, `termination_reason`, and `failure_reason` follow the per-event enum values in `analytics_schema/device.yaml`. Do not extend these values without a schema and Tracking Plan update.

### Device Usage Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Trigger wear, BT, BLE, charging, media playback, call, audio recording, video recording, AI Chat, photo capture, battery warning/sample, and media sync flows.
- Confirm every `device_usage_*_started` event fires once at session start and every terminal `*_ended` or `*_failed` event fires once for the same controlled session.
- Confirm terminal duration events include `duration_ms` and the correct state, interaction, or audio `duration_bucket` family.
- Confirm media sync state/failure events use only approved `sync_state`, `error_source`, `failure_reason`, and `item_count_bucket` values.
- Confirm all Device Usage events route through `DeviceUsageAnalyticsReporter` and the Android analytics tracker/adapter.
- Confirm no event contains device name, BLE/MAC address, serial number, raw sensor data, raw battery stream, raw BT/BLE state, raw command payload, media file name, chat content, transcript, audio/video/image content, raw error, stack trace, log content, or precise location.

### Device Usage iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Implement and verify the same `device_usage_*` event names, required properties, optional properties, enum values, privacy boundaries, and duration bucket families as Android.
- Confirm GA4 can split shared Device Usage events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm iOS reports terminal duration events with `duration_ms` and the same bucket values as Android.
- Confirm all Device Usage events route through the iOS analytics facade/adapter and no event contains device name, BLE/MAC address, serial number, raw sensor data, raw battery stream, raw BT/BLE state, raw command payload, media file name, chat content, transcript, audio/video/image content, raw error, stack trace, log content, or precise location.

### Device Usage Report Usage

- Wear and connectivity funnels: started/ended pairs for wear, BT, BLE, charging, media playback, and call sessions.
- Capture reliability: photo/video/audio success and failure rates split by `failure_reason`, `battery_level`, and connectivity flags.
- Device-origin AI Chat funnel: `device_usage_ai_chat_started` -> `device_usage_ai_chat_ended` or `device_usage_ai_chat_failed`, split by `voice_source`, `termination_reason`, and `failure_reason`.
- Power health dashboard: `device_usage_battery_warning_triggered` and `device_usage_battery_state_sampled` by `warning_kind`, `battery_change_type`, `battery_level`, and `charging`.
- Media sync pipeline: `device_usage_media_sync_state_changed` and `device_usage_media_sync_failed` by `sync_state`, `error_source`, `failure_reason`, and `item_count_bucket`.

## Chat Production Slice

The Chat slice v1 is intentionally narrowed to the minimum cross-platform GA4 contract needed for entry, text/image response, voice, and feedback reporting. All P0 events below are defined in `analytics_schema/chat.yaml`; P1/P2 rows are backlog guidance only and must not be implemented until they are promoted into the schema.

The production contract keeps `chat_` as the owner prefix, but event names describe stable Android/iOS implementation boundaries rather than broad business-completion wording. Android and iOS must use the same event names, required properties, optional properties, and shared enum values; platform-only enum values must be explicitly documented and must not be emitted by unsupported clients. Do not emit both deprecated draft names and canonical v1 names for the same behavior.

Android P0 is implemented in Enter-Glass-Android PR #390 (`codex/analytics-foundation-chat-p0`) with the 9 events in `analytics_schema/chat.yaml`. iOS is not marked complete yet; it should implement the same schema later without reintroducing the older full-draft event names from Feishu.

### Chat Priority Model

| Priority | Meaning | Implementation Rule |
| --- | --- | --- |
| P0 | Core Chat production telemetry | Present in `analytics_schema/chat.yaml`; Android is complete in PR #390, and iOS should target the same 9-event contract next. |
| P1 | Useful but not required for first launch | Keep in this Tracking Plan backlog; promote only with a schema update and matching cross-platform code boundaries. |
| P2/Future | Specialty or unstable instrumentation | Do not implement until the product question and platform event source are stable. |

### Chat P0 Event Contract

| Event | Priority | Trigger | Required Properties |
| --- | --- | --- | --- |
| `chat_list_viewed` | P0 | User opens Chat and the conversation list or default conversation region becomes visible. | `entry_point`, `surface` |
| `chat_session_opened` | P0 | The app opens a default, historical, or restored Chat session. | `surface`, `open_mode` |
| `chat_message_sent` | P0 | User submits a text message or a message with image attachments into Chat. | `surface`, `message_mode` |
| `chat_response_completed` | P0 | AI response stream/request completes normally and a user-visible response result is formed. | `surface`, `message_mode` |
| `chat_response_failed` | P0 | AI response request/stream or pre-response image preparation fails, times out, is cancelled, or is interrupted before a normal completed result. | `failure_reason`, `surface`, `message_mode` |
| `chat_voice_started` | P0 | Voice Chat successfully enters the accepted starting or active boundary from Android app/device/KWS paths or iOS app/device/Siri/KWS paths. | `entry_point`, `surface`, `voice_source` |
| `chat_voice_start_failed` | P0 | Voice Chat fails before entering the accepted starting or active boundary. | `failure_reason`, `surface`, `voice_source` |
| `chat_voice_ended` | P0 | A voice session that previously started terminates. Android currently emits user stop, hardware command, system interrupt, and audio timeout; iOS/future sources may emit the remaining approved terminal reasons. | `surface`, `voice_source`, `termination_reason` |
| `chat_feedback_submitted` | P0 | User submits quick feedback or report issue from a Chat message or detail surface. | `surface`, `feedback_action` |

### Chat P1 Backlog

| Event / Family | Priority | Rationale |
| --- | --- | --- |
| `chat_list_load_failed` | P1 | 只有当列表加载失败需要单独看入口质量时再加；首批可并入页面错误日志或后续治理。 |
| `chat_response_started` | P1 | 只有要做响应时延或 started/completed 精细漏斗时再加；首批用 `chat_message_sent` 做分母。 |
| `chat_image_upload_started/completed/failed` | P1 | 只有要单独分析图片上传可靠性时再拆；首批用 `message_mode=image` 和 `chat_response_failed(failure_reason=upload_failed/file_missing/decode_error)` 覆盖。 |
| `chat_session_action_requested/completed/failed` | P1 | 新会话、历史会话、删除、中断等属于二级操作分析，首批不进入核心漏斗。 |
| `chat_feedback_completed/failed` | P1 | report issue 后端成功率需要独立报表时再补；首批只量用户提交意图。 |
| `chat_kws_wake_triggered/failed` | P1 | 如果要单独看 KWS wake 接受率再补；首批通过 `voice_source=kws_wake` 体现在 voice 事件里。 |

### Chat P2 And Deferred Items

| Event / Family | Priority | Rationale |
| --- | --- | --- |
| `chat_tool_call_started/completed` | P2 | 等两端都有稳定、低基数、无参数内容的 tool 事件源后再纳入。 |
| `chat_encrypted_response_viewed/toggled` | P2 | 属于隐私功能使用分析，低于核心 Chat 漏斗优先级。 |
| `chat_tool_call_failed` | Future | 当前两端没有稳定 tool failure 边界，继续 deferred。 |
| `chat_memory_action_*` | Future | Memory 管理不放 Chat；未来应走 `memory_*` 或 Settings 归属。 |
| `chat_shortcut_*` | Future | 不单独定义；iOS Siri/AppIntent 通过 `voice_source=siri_shortcut` 或 `entry_point=app_shortcut` 表达，Android 不发送 `siri_shortcut`。 |
| `chat_kws_toggle_updated` | Do not add | 归属 `device_setting_updated(setting_type=kws_toggle)`，Chat 不重复定义。 |

Deprecated draft names remain non-canonical: `chat_voice_completed`, `chat_voice_failed`, `chat_image_started`, `chat_image_completed`, `chat_image_failed`, `chat_switch_*`, `chat_memory_action_*`, `chat_kws_toggle_updated`, `chat_shortcut_*`, and `chat_tool_call_failed`. Do not emit them from App code.

### Chat GA4 Custom Definitions

Recommended event-scoped custom dimensions for the P0 schema:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS Chat behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `entry_point` | P0 | Compare formal Chat entry paths without platform-specific event names |
| `surface` | P0 | Keep Chat events scoped to the Chat surface while preserving unknown fallback |
| `open_mode` | P0 | Split default, historical, and restored session opens |
| `message_mode` | P0 | Split text and image Chat response funnels |
| `voice_source` | P0 | Split device Bluetooth, app voice chat, iOS Siri shortcut, and KWS wake starts |
| `termination_reason` | P0 | Analyze voice terminal outcomes without separate platform event names |
| `feedback_action` | P0 | Split thumbs up, thumbs down, and issue reports |
| `feedback_issue_type` | P1 | Analyze issue categories without collecting free-text descriptions |
| `feedback_issue_count_bucket` | P1 | Support multi-select feedback analysis without GA4 arrays or event over-counting |
| `trigger_source` | P1 | Distinguish user, system, device, and server-push triggered behavior where reliable |
| `failure_reason` | P0 | Build failure breakdowns for response and voice failures |

v1 does not define custom metrics. Response duration, voice duration, image upload duration, and tool duration should be added later as terminal-event `*_duration_ms` metrics only after Android and iOS can record the same start/end boundaries.

Do not register or upload conversation ids, chat titles, message ids, chat text, prompts, answers, transcript text, audio content, image content, image URLs, file names, memory text, encrypted plaintext/decrypted plaintext, tool arguments, shortcut command text, raw system payloads, raw errors, request ids, response bodies, email, nickname, serial number, or stack traces.

### Chat Allowed Values

Chat-specific enum values used by the P0 schema (see `analytics_schema/chat.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `entry_point` | `chat_tab`, `home`, `device`, `kws`, `siri_shortcut`, `app_shortcut`, `deep_link`, `push`, `system_share`, `unknown` |
| `surface` | `chat`, `unknown` |
| `trigger_source` | `user`, `system`, `device`, `server_push`, `unknown` |
| `open_mode` | `default_session`, `history_session`, `restored_session`, `unknown` |
| `message_mode` | `text`, `image`, `unknown` |
| `voice_source` | `device_bluetooth`, `app_voice_chat`, `kws_wake`, `unknown`; `siri_shortcut` is iOS-only |
| `termination_reason` | Android current subset: `manual_stop`, `hardware_command`, `system_interrupt`, `audio_timeout`; cross-platform allowed values also include `ai_completed`, `rtc_failed`, `remote_disconnect`, `credits_exhausted`, `connection_timeout`, `hardware_disconnect`, `tool_execution_completed`, `unknown` |
| `feedback_action` | `thumbs_up`, `thumbs_down`, `report_issue` |
| `feedback_issue_type` | `couldnt_hear_me`, `misheard_me`, `interrupted_me`, `responded_too_slowly`, `voice_didnt_sound_right`, `didnt_like_responses`, `other`, `multiple`, `unknown` |
| `feedback_issue_count_bucket` | `0`, `1`, `2`, `3_plus` |
| `failure_reason` | `network_error`, `permission_denied`, `validation_failed`, `timeout`, `unauthorized`, `cancelled`, `interrupted`, `unsupported_state`, `device_disconnected`, `upload_failed`, `file_missing`, `decode_error`, `unsupported_format`, `sdk_error`, `unknown` |

Feedback multi-select rule: `chat_feedback_submitted` is emitted once per user submission. If one issue type is selected, send that `feedback_issue_type`; if multiple issue types are selected, send `feedback_issue_type=multiple` and a `feedback_issue_count_bucket`. Do not send GA4 arrays and do not emit multiple submitted events for one feedback form.

### Chat Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Enter Chat from tab and Home; confirm `chat_list_viewed` and `chat_session_opened` fire once and use approved `entry_point`, `surface`, and `open_mode` values.
- Send a text message; confirm `chat_message_sent -> chat_response_completed(message_mode=text)` for success.
- Send a message with an image attachment; confirm `message_mode=image` and use `chat_response_failed` with `failure_reason=upload_failed`, `file_missing`, `decode_error`, or `unsupported_format` for image preparation failures.
- Simulate response network, timeout, cancellation, and unsupported-state failures; confirm `chat_response_failed` uses approved `failure_reason` values and does not also emit `chat_response_completed` for the same attempt.
- Start voice Chat from app voice, device Bluetooth, and KWS where supported; confirm `chat_voice_started` uses approved Android `voice_source` values.
- Confirm Android does not emit `voice_source=siri_shortcut`; Android has no `VoiceChatSource.SIRI_SHORTCUT` source.
- Simulate pre-start voice permission, RTC setup, KWS post-wake, and unsupported-state failures; confirm `chat_voice_start_failed` is emitted without `chat_voice_started` for the same attempt.
- End an already-started Android voice session through manual stop, hardware command, system interrupt, and audio timeout where supported; confirm `chat_voice_ended` uses only the Android current `termination_reason` subset.
- Confirm Android does not emit `ai_completed`, `rtc_failed`, `remote_disconnect`, `credits_exhausted`, `connection_timeout`, `hardware_disconnect`, `tool_execution_completed`, or `unknown` until a real Android event source is implemented.
- Submit thumbs up, thumbs down, single-issue, and multi-issue feedback; confirm `feedback_action`, `feedback_issue_type`, and `feedback_issue_count_bucket` follow the schema rules.
- Confirm all Chat events route through the Android analytics tracker/adapter and no event contains chat text, prompt text, answer text, transcript text, audio, image content, memory content, encrypted/decrypted plaintext, tool arguments, command text, ids, raw errors, or stack traces.

### Chat iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same P0 Chat event set as Android using the same event names, required properties, optional properties, and enum values from `analytics_schema/chat.yaml`.
- Confirm GA4 can split shared Chat events by `platform=android` and `platform=ios` without platform-specific event names.
- Verify default, history, and restored session opens use the same `open_mode` values as Android.
- Verify text and image response success/failure chains use `chat_message_sent`, `chat_response_completed`, and `chat_response_failed` with the same `message_mode` values as Android.
- Verify Siri/AppIntent/App Shortcut voice paths use the iOS-only `voice_source=siri_shortcut`; KWS/Hey Memo paths use `voice_source=kws_wake`.
- Verify report issue feedback does not upload description, email, nickname, serial number, or raw API payload to GA4; multi-select issue feedback follows the single-event bucketing rule.
- Confirm all Chat events route through the iOS analytics facade/adapter and no event contains chat text, prompt text, answer text, transcript text, audio, image content, memory content, encrypted/decrypted plaintext, tool arguments, command text, ids, raw errors, or stack traces.

### Chat Report Usage

- Entry funnel: `chat_list_viewed` -> `chat_session_opened`, split by `entry_point`, `open_mode`, and `platform`.
- Text/image response funnel: `chat_message_sent` -> `chat_response_completed` or `chat_response_failed`, split by `message_mode`, `failure_reason`, and `platform`.
- Voice funnel: `chat_voice_started` -> `chat_voice_ended`, split by `voice_source`, `termination_reason`, and `platform`; pre-start blocks use `chat_voice_start_failed`.
- Feedback distribution: `chat_feedback_submitted` by `feedback_action`, `feedback_issue_type`, `feedback_issue_count_bucket`, and `platform`.

## Media Production Slice

The Media slice covers the formal device-to-app media import, browse/share/delete, auto horizon correction, and image enhancement flows. All events below are defined in `analytics_schema/media.yaml`.

Horizon correction, image enhancement, playback, share, delete, and import events use the `media_` prefix to align with the prefix taxonomy. The share flow intentionally measures only the app-observable boundary: `media_share_sheet_opened` means the system share UI was opened successfully, not that the third-party target app actually sent or delivered the media.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `media_import_ready` | media | Android+iOS | A visible Home or Photos/Media Library surface shows the pending-media import entry; do not emit from background count notifications alone | `surface`, `trigger_source` |
| `media_import_started` | media | Android+iOS | User starts the formal import after pre-start gates pass | `entry_point`, `trigger_source`, `surface` |
| `media_import_completed` | media | Android+iOS | Import completes with at least one media item inserted and no known per-item failures | `surface`, `trigger_source` |
| `media_import_degraded` | media | Android+iOS | Import batch is usable but one or more media items were skipped or failed locally | `failure_reason`, `surface`, `trigger_source` |
| `media_import_failed` | media | Android+iOS | Started import flow ends without a usable completed batch, including empty batches with zero successful items | `failure_reason`, `surface` |
| `media_import_blocked` | media | Android+iOS | Import opportunity is blocked before the import starts by permission, connectivity, or device-state gates | `failure_reason`, `surface` |
| `media_import_cancelled` | media | Android+iOS | User explicitly cancels an in-progress import | `surface`, `trigger_source` |
| `media_library_viewed` | media | Android+iOS | User enters the Photos/media library list; detail pages do not reuse this event | `entry_point`, `surface` |
| `media_detail_viewed` | media | Android+iOS | User opens a single media detail page | `entry_point`, `surface`, `media_type` |
| `media_share_started` | media | Android+iOS | User initiates a share from a detail page or batch selection | `surface`, `trigger_source`, `selection_scope` |
| `media_share_sheet_opened` | media | Android+iOS | App prepares share items and opens the system share UI successfully | `surface`, `trigger_source`, `selection_scope` |
| `media_delete_started` | media | Android+iOS | User initiates a delete from detail or batch selection | `surface`, `trigger_source`, `selection_scope` |
| `media_delete_completed` | media | Android+iOS | Delete API returns success; do not emit from optimistic UI state | `surface`, `trigger_source`, `selection_scope` |
| `media_action_failed` | media | Android+iOS | Delete or share action fails before completing locally | `failure_reason`, `surface`, `action_type` |
| `media_playback_started` | media | Android+iOS | Video detail playback actually starts, such as first frame rendered or player ready+playing | `surface`, `media_type` |
| `media_playback_failed` | media | Android+iOS | Video detail playback cannot start | `failure_reason`, `surface`, `media_type` |
| `media_horizon_viewed` | media | Android+iOS | User opens an image detail with horizon correction available | `entry_point`, `surface` |
| `media_horizon_toggled` | media | Android+iOS | User toggles the horizon correction on/off and a visible result is rendered | `surface`, `trigger_source` |
| `media_horizon_export_failed` | media | Android+iOS | Detail or share path fails to output a horizon-corrected result and cannot safely fall back | `failure_reason`, `surface` |
| `media_enhance_toggled` | media | Android+iOS | User toggles image enhancement on/off in builds where the control is visible | `surface`, `trigger_source` |

### Media GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS media behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `failure_reason` | P0 | Build failure breakdowns for import, share, delete, playback, and horizon correction export |
| `surface` | P0 | Split media behavior by home, photos, gallery, and detail surfaces |
| `action_type` | P0 | Split delete vs share failures within `media_action_failed` |
| `entry_point` | P1 | Compare where users enter media flows |
| `trigger_source` | P1 | Distinguish user-, system-, and device-triggered media flows |
| `import_source` | P1 | Distinguish primary device-capture import from manual retry |
| `selection_scope` | P1 | Distinguish single-detail vs batch share/delete |
| `item_count_bucket` | P1 | Bucketed import size distribution |
| `media_type` | P1 | Split image, video, audio, mixed, and unknown media flows |
| `playback_source` | P1 | Split video playback source without exposing media paths |
| `toggle_state` | P1 | Horizon correction and image enhancement usage preference (on vs off) |

Do not register media path, file names, thumbnails, raw capture time, EXIF data, device address, share targets, raw transfer errors, raw player state, playback progress, raw duration, raw exceptions, or stack traces.

### Media Allowed Values

Media-specific enum values (see `analytics_schema/media.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `import_source` | `device_capture`, `manual_retry`, `unknown` |
| `selection_scope` | `single`, `batch`, `unknown` |
| `action_type` (media_action_failed) | `delete`, `share`, `unknown` |
| `item_count_bucket` | `1`, `2_5`, `6_20`, `21_100`, `100_plus`, `unknown` |
| `media_type` | `image`, `video`, `audio`, `mixed`, `unknown`; playback events allow `video` only |
| `playback_source` | `local_file`, `cached_file`, `unknown` |
| `toggle_state` (horizon and enhance) | `on`, `off`, `unknown` |

`entry_point`, `surface`, `trigger_source`, and `failure_reason` follow the shared enum values defined per event in `analytics_schema/media.yaml`. Do not extend these values without a Tracking Plan update.

### Media Failure Reason Mapping (Android)

`MediaSyncState.Error` subtypes from the Android codebase map to GA4 `failure_reason` enum values as follows:

| Code Error Subtype | failure_reason |
| --- | --- |
| `ChannelUnavailable` / `BatteryLow` / `CantSyncWhenCalling` / `CantSyncWhenOta` / `CantSyncWhenFactory` / `CantSyncWhenCharging` / `Busy` | `unsupported_state` |
| `Other` | `sdk_error` |
| WiFi or location permission denial | `permission_denied` |
| Network connectivity errors | `network_error` |
| Download timeout | `timeout` |
| Pre-start permission/connectivity/device-state gate | `media_import_blocked` with `permission_denied`, `network_error`, or `unsupported_state` |
| Per-item duplicate, missing file, decode failure, missing video sub media, or local item insertion failure while the batch remains usable | `media_import_degraded` with `validation_failed`, `file_missing`, `decode_error`, `unsupported_state`, or `sdk_error` |
| Started import produces zero successful items without a more specific SDK/download error | `media_import_failed` with `unknown` |

iOS implementation must map equivalent error states to the same `failure_reason` enum values to keep platform parity.

### Media Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Make a connected device report pending media and stay on Home; confirm `media_import_ready` appears once with `surface=home` before `media_import_started`.
- Open Photos/Media Library for the same pending opportunity; confirm `media_import_ready` appears only when the import entry is visible and uses `surface=media_library`.
- Confirm background service count notifications do not emit `media_import_ready` while no Home or Photos/Media Library import entry is visible.
- Trigger device-to-app media import from Home and from Photos entry; confirm `media_import_started` with the correct `entry_point` and `import_source=device_capture`.
- Trigger a manual retry; confirm `media_import_started` with `import_source=manual_retry`.
- Complete an import with at least one successfully inserted item; confirm `media_import_completed` with an approved `item_count_bucket`.
- Simulate a started import that produces zero successful items; confirm `media_import_failed` with `failure_reason=unknown` and confirm `media_import_completed` does NOT fire.
- Simulate partial item failure while the batch remains usable; confirm `media_import_degraded` with the correctly mapped `failure_reason`.
- Simulate permission denial before the import starts; confirm `media_import_blocked` and confirm `media_import_started` does NOT fire for the same attempt.
- Simulate channel unavailable, low battery, and download timeout after import starts; confirm `media_import_failed` with the correctly mapped `failure_reason`.
- Start an import and explicitly cancel mid-flight; confirm `media_import_cancelled` and confirm `media_import_failed` does NOT also fire for the same controlled cancellation.
- Open Photos list; confirm `media_library_viewed` for the list surface only.
- Open image and video detail pages; confirm `media_detail_viewed` with the correct `media_type` and confirm `media_library_viewed` is not reused for detail pages.
- Trigger share from a single detail and from a batch selection; confirm `media_share_started` with the correct `selection_scope`.
- Open the system share UI; confirm `media_share_sheet_opened`. Canceling the system share UI should not emit any share completion event.
- Trigger delete from a single detail and from a batch selection; confirm `media_delete_started` with the correct `selection_scope`.
- Complete a delete; confirm `media_delete_completed` only after the delete API returns success.
- Simulate a delete failure and a share failure; confirm `media_action_failed` with the correct `action_type` and an approved `failure_reason`.
- Open a video detail page and start playback; confirm `media_playback_started`.
- Simulate video file missing, decode failure, or unsupported format; confirm `media_playback_failed` with an approved `failure_reason` and confirm `media_playback_started` is not emitted for the same failed attempt.
- Open an image detail with horizon correction available; confirm `media_horizon_viewed`.
- Toggle horizon correction on and off; confirm `media_horizon_toggled` with the correct `toggle_state`.
- In a build/configuration where the enhancement control is visible, toggle image enhancement on and off; confirm `media_enhance_toggled` with the correct `toggle_state`.
- In a build/configuration where the enhancement control is hidden, confirm `media_enhance_toggled` is not emitted.
- Simulate a horizon correction export failure; confirm `media_horizon_export_failed` with an approved `failure_reason`.
- Confirm all media events route through the Android analytics tracker/adapter and no event contains media path, file names, thumbnails, raw capture time, EXIF, share targets, raw transfer errors, raw player state, playback progress, raw duration, raw exceptions, or stack traces.

### Media iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same media events as Android using the same event names, required properties, optional properties, and enum values.
- Confirm GA4 can split shared media events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm iOS error states map to the same `failure_reason` enum values as Android (no `network_unavailable` vs `network_error` drift).
- Confirm share reporting uses `media_share_sheet_opened` for system share UI presentation and does not attempt to report third-party share completion.
- Confirm all media events route through the iOS analytics facade/adapter and no event contains media path, file names, thumbnails, raw capture time, EXIF, share targets, raw transfer errors, raw player state, playback progress, raw duration, raw exceptions, or stack traces.

### Media Report Usage

- Import opportunity funnel: `media_import_ready` → `media_import_started` or `media_import_blocked`; started imports then resolve to `media_import_completed`, `media_import_degraded`, `media_import_failed`, or `media_import_cancelled`.
- Import failure breakdown: `media_import_failed`, `media_import_blocked`, and `media_import_degraded` by `failure_reason`, `import_source`, and `platform`.
- Import cancellation rate: `media_import_cancelled` over `media_import_started`.
- Import size distribution: import terminal events by `item_count_bucket`.
- Browse funnel: `media_library_viewed` → `media_detail_viewed`, split by `media_type`.
- Share funnel: `media_share_started` → `media_share_sheet_opened` or `media_action_failed` (`action_type=share`) by `selection_scope`.
- Delete funnel: `media_delete_started` → `media_delete_completed` or `media_action_failed` (`action_type=delete`) by `selection_scope`.
- Video playback start rate: `media_detail_viewed` (`media_type=video`) → `media_playback_started` or `media_playback_failed`.
- Playback failure breakdown: `media_playback_failed` by `failure_reason`, `playback_source`, and `platform`.
- Horizon correction toggle usage: `media_horizon_toggled` by `toggle_state` and `platform`.
- Image enhancement toggle usage: `media_enhance_toggled` by `toggle_state` and `platform`.
- Horizon correction export reliability: `media_horizon_export_failed` by `failure_reason` and `surface`.

## Reminder Production Slice

The Reminder slice covers formal Reminder list entry, formal save outcomes, Home due Reminder cards, due alert triggers, and due Reminder audio playback. All P0 events below are defined in `analytics_schema/reminder.yaml`.

This first production slice intentionally excludes lower-priority empty-state and help-link events: `reminder_entry_viewed`, `reminder_help_opened`, and `reminder_help_open_failed`. Calendar sync analytics also remains outside this module and should be governed by the separate Reminder Calendar sync plan.

Voice-created reminders are not a formal v1 analytics object. The `create` value in `action_type` is reserved only for a formal Reminder creation save boundary after App implementation confirms one.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `reminder_list_viewed` | reminder | Android+iOS | User enters the formal Reminder list screen; emit at most once per screen presentation | `entry_point`, `surface` |
| `reminder_saved` | reminder | Android+iOS | Formal create, edit, complete, reactivate, or delete operation reaches an accepted success boundary | `surface`, `trigger_source` |
| `reminder_save_failed` | reminder | Android+iOS | Formal create, edit, complete, reactivate, or delete operation fails, is blocked, or rolls back before success | `failure_reason`, `surface` |
| `reminder_due_card_viewed` | reminder | Android+iOS | Home displays a formal due Reminder card; emit once per card opportunity per Home screen presentation | `surface`, `trigger_source` |
| `reminder_due_card_opened` | reminder | Android+iOS | User taps a Home due Reminder card and navigation to Reminder handling is requested | `surface`, `trigger_source` |
| `reminder_due_card_dismissed` | reminder | Android+iOS | User closes a Home due Reminder card and the dismiss action is accepted | `surface`, `trigger_source` |
| `reminder_alert_triggered` | reminder | Android+iOS | A formal due Reminder triggers an accepted local notification path or server-push playback chain | `trigger_source`, `surface` |
| `reminder_playback_started` | reminder | Android+iOS | Due Reminder audio actually starts playback | `surface`, `trigger_source` |
| `reminder_playback_failed` | reminder | Android+iOS | Due Reminder audio cannot play before a successful start | `failure_reason`, `surface` |

### Reminder GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS Reminder behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `surface` | P0 | Split Reminder behavior by Home, Reminder, and background contexts |
| `trigger_source` | P0 | Distinguish user, system, and server-push triggered Reminder flows |
| `failure_reason` | P0 | Build save and playback failure breakdowns |
| `action_type` | P0 | Split formal create, edit, complete, reactivate, and delete outcomes |
| `alert_mode` | P0 | Split local notification, server-push, and audio playback chains |
| `entry_point` | P1 | Compare Home, notification, and background Reminder entry sources |

Do not register `build_type`, `app_version_name`, or `app_version_code` unless a later QA or version-regression report requires them. Do not register or upload reminder id, title, body, due time, time zone, notification body, audio URL, audio path, audio file name, raw push payload, raw server response, raw player state, raw error code, raw exception message, request id, response body, or stack trace.

### Reminder Allowed Values

Reminder-specific enum values (see `analytics_schema/reminder.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `entry_point` | `home`, `background`, `notification`, `unknown` |
| `surface` | `home`, `reminder`, `background`, `unknown` |
| `trigger_source` | `user`, `system`, `server_push`, `unknown` |
| `action_type` | `create`, `edit`, `complete`, `reactivate`, `delete`, `unknown` |
| `alert_mode` | `local_notification`, `server_push`, `audio`, `unknown` |
| `failure_reason` | `validation_failed`, `network_error`, `timeout`, `unauthorized`, `device_disconnected`, `file_missing`, `sdk_error`, `unsupported_state`, `unknown` |

Do not extend these values without a Tracking Plan and schema update. Map unknown or unmapped platform errors to `unknown`, not raw error text.

### Reminder Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Enter the Reminder list from Home and from a due Reminder card; confirm `reminder_list_viewed` appears once per screen presentation with approved `entry_point`, `surface`, and `trigger_source`.
- Create, edit, complete, reactivate, and delete a formal Reminder where supported; confirm `reminder_saved` appears only after the accepted success boundary.
- Simulate empty-title validation, network failure, unauthorized failure, timeout, and delete or update rollback where possible; confirm `reminder_save_failed` appears with approved `failure_reason` and `action_type`.
- Create or sync a due Reminder and open Home; confirm `reminder_due_card_viewed` appears when the card is visible and does not over-count the same card opportunity during recomposition, refresh, or scrolling.
- Tap a visible due Reminder card; confirm `reminder_due_card_opened` appears once with `trigger_source=user`.
- Close a visible due Reminder card; confirm `reminder_due_card_dismissed` appears after the dismiss action is accepted and does not also emit `reminder_due_card_opened`.
- Trigger `reminder_lifecycle` notification-sent or the equivalent due alert chain; confirm `reminder_alert_triggered` appears with `trigger_source=server_push` and `alert_mode=server_push`.
- Trigger due Reminder playback while glasses audio output is available; confirm `reminder_playback_started` appears only after audio playback actually starts, not when audio is merely enqueued or prepared.
- Trigger playback with missing audio, disconnected A2DP, player prepare failure, and player start failure where possible; confirm `reminder_playback_failed` appears with approved `failure_reason` and does not also emit `reminder_playback_started` for the same failed attempt.
- Confirm no Reminder event contains reminder id, title, body, due time, time zone, notification body, audio URL, audio path, audio file name, raw push payload, raw server response, raw player state, raw error code, raw exception, request id, response body, or stack trace.
- Confirm all Reminder events route through the Android analytics tracker/adapter and no business, feature, domain, or data code calls Firebase Analytics directly.

### Reminder iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same P0 Reminder event set as Android: `reminder_list_viewed`, `reminder_saved`, `reminder_save_failed`, `reminder_due_card_viewed`, `reminder_due_card_opened`, `reminder_due_card_dismissed`, `reminder_alert_triggered`, `reminder_playback_started`, and `reminder_playback_failed`.
- Confirm iOS uses the same event names, required properties, optional properties, enum values, and trigger boundaries as Android.
- Confirm GA4 can split shared Reminder events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm iOS save, alert, and playback errors map to the same `failure_reason` values as Android.
- Confirm iOS due card exposure uses the same de-duplication boundary as Android: once per card opportunity per Home screen presentation.
- Confirm iOS playback start means actual playback starts, not enqueue, cache hit, or prepare-only state.
- Confirm all Reminder events route through the iOS analytics facade/adapter and no event contains reminder id, title, body, due time, time zone, notification body, audio URL, audio path, audio file name, raw push payload, raw server response, raw player state, raw error code, raw exception, request id, response body, or stack trace.

### Reminder Report Usage

- Reminder entry funnel: `reminder_list_viewed` by `entry_point`, `surface`, `platform`, `environment`, and `build_region`.
- Save success and failure rate: `reminder_saved` vs `reminder_save_failed`, split by `action_type`, `failure_reason`, `surface`, and `platform`.
- Due card funnel: `reminder_due_card_viewed` -> `reminder_due_card_opened` or `reminder_due_card_dismissed`, split by `platform`.
- Alert-to-playback funnel: `reminder_alert_triggered` -> `reminder_playback_started` or `reminder_playback_failed`, split by `alert_mode`, `failure_reason`, and `platform`.
- Playback failure breakdown: `reminder_playback_failed` by `failure_reason`, `surface`, and `platform`.

## Notes Production Slice

The Notes slice covers Notes list/tag filtering, detail opens, recording, import, processing/generation, settings, export/share, deletion, summary version selection, and speaker-label actions. All P0/P1 events below are defined in `analytics_schema/note.yaml`.

This slice keeps the Feishu Tracking Plan's plural event names for list/settings (`notes_list_viewed`, `notes_setting_*`) and speaker-label names (`speaker_label_*`), and uses `note_` for single-Note actions. The validator allows `notes_` and `speaker_label_` as Notes-owner exceptions for these approved names only.

### Notes Event Priority

| Priority | Event |
| --- | --- |
| P0 | `notes_list_viewed`, `note_detail_viewed`, `note_recording_started`, `note_recording_completed`, `note_recording_failed`, `note_import_started`, `note_import_completed`, `note_import_failed`, `note_processing_completed`, `note_processing_failed`, `note_generation_submitted`, `notes_setting_viewed`, `notes_setting_updated`, `notes_setting_failed` |
| P1 | `note_export_started`, `note_export_completed`, `note_export_failed`, `note_deleted`, `note_delete_failed`, `note_summary_version_selected`, `note_speaker_label_evaluated`, `note_speaker_label_completed`, `note_speaker_label_blocked` |

`notes_empty_tutorial_viewed`, `notes_empty_tutorial_opened`, and `notes_empty_tutorial_load_failed` remain deferred until the App has a formal empty-state tutorial surface separate from the normal Notes list/product funnel.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `notes_list_viewed` | note | Android+iOS | User enters Notes list or changes the visible Notes tag filter | `entry_point`, `surface`, `note_filter` |
| `note_detail_viewed` | note | Android+iOS | User opens one Note detail page and the detail surface becomes visible | `surface`, `note_type` |
| `note_recording_started` | note | Android+iOS | Notes recording start is accepted and a local recording draft/session is created | `surface`, `recording_source` |
| `note_recording_completed` | note | Android+iOS | Started Notes recording stops successfully and finalization proceeds | `surface`, `recording_source`, `note_type` |
| `note_recording_failed` | note | Android+iOS | Notes recording start, stop, or finalization fails before successful finalization | `failure_reason`, `surface`, `recording_source` |
| `note_import_started` | note | Android+iOS | User or system submits an audio file into Notes import and validation starts | `surface`, `import_source` |
| `note_import_completed` | note | Android+iOS | Imported audio passes validation and a local Note is created or queued | `surface`, `import_source`, `note_type` |
| `note_import_failed` | note | Android+iOS | Imported audio is rejected or import fails before a local Note is accepted | `failure_reason`, `surface`, `import_source` |
| `note_processing_completed` | note | Android+iOS | Note processing reaches successful transcript, summary, or speaker-label result | `surface`, `note_type`, `processing_type` |
| `note_processing_failed` | note | Android+iOS | Transcript, summary, or speaker-label processing reaches a failed or blocked terminal state | `failure_reason`, `surface`, `note_type`, `processing_type` |
| `note_generation_submitted` | note | Android+iOS | User taps Generate/Re-generate and the request is accepted for processing | `surface`, `note_type`, `generation_type` |
| `notes_setting_viewed` | note | Android+iOS | User opens Notes settings and the settings surface becomes visible | `surface` |
| `notes_setting_updated` | note | Android+iOS | User changes a Notes setting and the new value is accepted/persisted | `surface`, `setting_type` |
| `notes_setting_failed` | note | Android+iOS | Notes setting change is rejected, fails to persist, or rolls back | `failure_reason`, `surface`, `setting_type` |
| `note_export_started` | note | Android+iOS | User starts an export/share action for a Note and the request is accepted | `surface`, `note_type`, `export_type` |
| `note_export_completed` | note | Android+iOS | Notes export/share preparation succeeds and the share sheet or saved artifact is available | `surface`, `note_type`, `export_type` |
| `note_export_failed` | note | Android+iOS | Notes export/share preparation or share sheet presentation fails before success | `failure_reason`, `surface`, `note_type`, `export_type` |
| `note_deleted` | note | Android+iOS | User confirms single or batch deletion and the delete operation completes successfully | `surface`, `note_type`, `delete_scope` |
| `note_delete_failed` | note | Android+iOS | User-confirmed single or batch deletion fails or rolls back before success | `failure_reason`, `surface`, `note_type`, `delete_scope` |
| `note_summary_version_selected` | note | Android+iOS | User selects a generated summary version and the selected version becomes visible | `surface`, `note_type`, `version_count_bucket` |
| `note_speaker_label_evaluated` | note | Android+iOS | Note detail evaluates whether speaker labels are available, pending, or blocked | `surface`, `note_type` |
| `note_speaker_label_completed` | note | Android+iOS | Speaker label generation or rename reaches an accepted successful result | `surface`, `note_type` |
| `note_speaker_label_blocked` | note | Android+iOS | Speaker-label generation or rename is blocked, fails, or rolls back before success | `failure_reason`, `surface`, `note_type` |

### Notes GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS Notes behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `note_filter` | P0 | Split Notes list usage by All, Recording, Memo, and Call filters |
| `note_type` | P0 | Split single-Note behavior by Recording, Memo, Call, Mixed, or Unknown |
| `failure_reason` | P0 | Build failure breakdowns without raw errors |
| `surface` | P0 | Split list, detail, recording, import, settings, share, and background surfaces |
| `processing_type` | P0 | Split transcript, summary, and speaker-label processing |
| `setting_type` | P0 | Split Notes settings changes without sending values |
| `entry_point` | P1 | Compare Home, tab, notification, deep link, list, and share entries |
| `recording_source` | P1 | Split App button, glasses shortcut, and automatic call recording starts |
| `import_source` | P1 | Split system share, file picker, retry, and recovered import tasks |
| `generation_type` | P1 | Split Summary, Transcript, and Reminder generation requests |
| `export_type` | P1 | Split audio, transcript, summary, PDF, text, and share actions |
| `delete_scope` | P1 | Split single and batch deletion |
| `version_count_bucket` | P1 | Bucket summary version choices without raw ids or counts |
| `trigger_source` | P1 | Distinguish user, system, and device-triggered Notes actions |

Do not register or upload note id, title, transcript text, summary text, speaker names, raw speaker maps, audio paths, file names, source app names, share targets, contact names, phone numbers, location/address/latitude/longitude, raw locale strings, language labels, previous/new setting values, request ids, response bodies, raw server errors, raw exception messages, or stack traces.

### Notes Allowed Values

Notes-specific enum values (see `analytics_schema/note.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `note_filter` | `all`, `recording`, `memo`, `call`, `unknown` |
| `note_type` | `recording`, `memo`, `call`, `mixed`, `unknown` |
| `surface` | `notes_list`, `note_detail`, `note_recording`, `note_import`, `notes_settings`, `background`, `share_sheet`, `unknown` |
| `entry_point` | `home`, `notes_tab`, `notes_list`, `notification`, `deep_link`, `system_share`, `unknown` |
| `recording_source` | `app_record_button`, `glasses_shortcut`, `auto_call_recording`, `unknown` |
| `import_source` | `system_share`, `file_picker`, `manual_retry`, `recovered_task`, `unknown` |
| `processing_type` | `transcript`, `summary`, `speaker_label`, `unknown` |
| `generation_type` | `summary`, `transcript`, `reminder`, `unknown` |
| `setting_type` | `transcription_language`, `summary_language`, `auto_summary`, `auto_call_recording`, `unknown` |
| `toggle_state` | `on`, `off`, `unknown` |
| `export_type` | `audio`, `transcript`, `summary`, `pdf`, `text`, `share`, `unknown` |
| `delete_scope` | `single`, `batch`, `unknown` |
| `version_count_bucket` | `one`, `two_to_five`, `six_to_twenty`, `more_than_twenty`, `unknown` |
| `failure_reason` | Shared low-cardinality values such as `validation_failed`, `network_error`, `timeout`, `unauthorized`, `permission_denied`, `file_too_large`, `file_too_short`, `unsupported_format`, `device_disconnected`, `file_missing`, `sdk_error`, `unsupported_state`, `user_cancelled`, and `unknown` |

Do not extend these values without a Tracking Plan and schema update. Map unmapped platform errors to `unknown`, not raw error text.

### Notes Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Open Notes list and switch All, Recording, Memo, and Call filters; confirm `notes_list_viewed` carries `note_filter`.
- Open Recording, Memo, and Call details; confirm `note_detail_viewed` carries `note_type` without ids or content.
- Start, stop, and fail a Notes recording where possible; confirm `note_recording_started`, `note_recording_completed`, and `note_recording_failed` fire at accepted boundaries only.
- Import audio through supported Android entries; confirm `note_import_started`, `note_import_completed`, and `note_import_failed` split accepted, success, and failure states.
- Trigger transcript/summary/speaker-label processing; confirm `note_processing_completed`, `note_processing_failed`, and `note_generation_submitted` use approved enum values.
- Open Notes settings and change supported settings; confirm `notes_setting_viewed`, `notes_setting_updated`, and `notes_setting_failed` do not send values or raw locales.
- Exercise export/share, delete, summary version selection, and speaker-label actions; confirm P1 events fire only after accepted boundaries.
- Confirm all Notes events route through the Android analytics tracker/adapter and do not alter existing Notes control flow.

### Notes iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same P0/P1 Notes event set as Android using the same event names, required properties, optional properties, enum values, and trigger boundaries.
- Confirm GA4 can split shared Notes events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm iOS errors map to the same `failure_reason` values as Android.
- Confirm list filter reporting uses `note_filter=all|recording|memo|call`, and single-Note reporting uses `note_type=recording|memo|call`.
- Confirm all Notes events route through the iOS analytics facade/adapter and no event contains note content, ids, speaker names, audio paths, file names, contact names, location, raw errors, request ids, response bodies, or stack traces.

### Notes Report Usage

- Notes entry/filter usage: `notes_list_viewed` by `note_filter`, `entry_point`, `surface`, `platform`, `environment`, and `build_region`.
- Recording funnel: `note_recording_started` -> `note_recording_completed` or `note_recording_failed` by `recording_source`, `note_type`, and `failure_reason`.
- Import funnel: `note_import_started` -> `note_import_completed` or `note_import_failed` by `import_source`, `note_type`, and `failure_reason`.
- Processing reliability: `note_processing_completed` vs `note_processing_failed` by `processing_type`, `generation_type`, `note_type`, and `platform`.
- Generation usage: `note_generation_submitted` by `generation_type`, `note_type`, and `platform`.
- Settings usage: `notes_setting_viewed`, `notes_setting_updated`, and `notes_setting_failed` by `setting_type`, `toggle_state`, and `failure_reason`.
- P1 actions: export/share, deletion, summary version, and speaker-label funnels by their event-specific dimensions.

## Tutorial Production Slice

The Tutorial slice covers the formal Tutorial screen shared by first-run onboarding and Home tutorial cards, plus tutorial-owned help links. All v1 events below are defined in `analytics_schema/tutorial.yaml`.

The Feishu requirement draft used mixed names such as `onboarding_tutorial_*`, `tutorial_*`, and `help_link_*`. The production contract canonicalizes this module to the `tutorial_` prefix so Android and iOS can share one taxonomy. App code must not emit the draft names and the canonical names for the same behavior.

### Tutorial Code-Inferred Scope

Android currently uses one shared `DeviceTutorial(tutorialId)` route for both the first-run Full tutorial and Home tutorial cards. Because the route carries only `tutorialId`, v1 attribution must either be reported at each navigation site or the route must be extended with `entry_point` / `trigger_source` metadata before App implementation.

The formal TutorialId set maps to `tutorial_id` values: `full`, `overview`, `ai`, `wear_glasses`, `control_music`, `capture`, `call`, `memory`, `translate`, `reminder`, `quick_notes`, `recording_notes`, `voice_commands`, `power`, and `unknown`. Use `tutorial_category=onboarding` for `full`, `tutorial_category=device` for device-operation cards, and `tutorial_category=memo_ai` for Memo AI cards including Reminder.

Current Android Home cards open directly without a card-level eligibility gate, so `tutorial_card_open_blocked` is not part of v1. Tutorial media is rendered through image/video components, but the public tutorial component does not yet expose reliable start, completion, or failure callbacks for GA4. Therefore `tutorial_media_started`, `tutorial_media_completed`, and `tutorial_media_failed` are deferred until the App adds player callbacks or replaces them with page-level events such as `tutorial_step_viewed` / `tutorial_step_completed`. Android also has no reliable return attribution after an external help link is opened, so `tutorial_help_link_returned` is deferred.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `tutorial_center_viewed` | tutorial | Android+iOS | Home renders the Tutorials section or a Tutorials tab becomes the selected visible category | `entry_point`, `surface`, `tutorial_category` |
| `tutorial_card_opened` | tutorial | Android+iOS | User taps a Home tutorial card and navigation to the Tutorial screen is requested | `tutorial_id`, `tutorial_category`, `entry_point`, `surface`, `trigger_source` |
| `tutorial_flow_started` | tutorial | Android+iOS | Shared Tutorial screen receives a tutorial route, builds pages, and the first page becomes visible | `tutorial_id`, `tutorial_category`, `entry_point`, `surface`, `trigger_source` |
| `tutorial_flow_completed` | tutorial | Android+iOS | User reaches the final tutorial page or presses the final primary action and exits through the completed path | `tutorial_id`, `tutorial_category`, `entry_point`, `surface`, `trigger_source` |
| `tutorial_flow_interrupted` | tutorial | Android+iOS | User exits before completion or a required tutorial action fails and prevents normal completion | `tutorial_id`, `tutorial_category`, `failure_reason`, `entry_point`, `surface`, `trigger_source` |
| `tutorial_help_link_opened` | tutorial | Android+iOS | User taps a tutorial-owned help link and the open action is accepted | `tutorial_id`, `tutorial_category`, `help_type`, `entry_point`, `surface`, `trigger_source` |
| `tutorial_help_link_open_failed` | tutorial | Android+iOS | User taps a tutorial-owned help link and the open action fails | `tutorial_id`, `tutorial_category`, `help_type`, `failure_reason`, `entry_point`, `surface` |

### Tutorial Deferred Events

The following draft events are intentionally not in v1:

| Deferred Event | Reason | Promotion Condition |
| --- | --- | --- |
| `tutorial_card_open_blocked` | Home tutorial cards currently have no card-level gate in Android code. | Add a formal eligibility or asset gate before navigation and define failure mapping. |
| `tutorial_media_started` / `tutorial_media_completed` / `tutorial_media_failed` | Tutorial media is local image/video content, but current public tutorial UI does not expose reliable GA4 callbacks. | Add player/page callbacks with stable semantics, or replace with `tutorial_step_*` events. |
| `tutorial_help_link_returned` | Opening external help links has no reliable origin-preserving return attribution in current code. | Add lifecycle return tracking tied to a pending tutorial help-link context. |

### Tutorial GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS tutorial behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `tutorial_id` | P0 | Split funnels by the concrete route-level tutorial id |
| `tutorial_category` | P0 | Roll up tutorial ids into onboarding, device, and Memo AI categories |
| `failure_reason` | P0 | Build interruption and help-link failure breakdowns |
| `surface` | P0 | Split tutorial behavior by Home, onboarding, and Tutorial screen contexts |
| `entry_point` | P1 | Compare where users enter tutorial flows and help links |
| `trigger_source` | P1 | Distinguish user-triggered Home card opens from system-triggered first-run presentation |
| `help_type` | P1 | Split tutorial-owned help link categories such as Voice Commands |

Do not register or upload tutorial copy, card titles, localized text, media URLs, thumbnails, file names, playback position, exact playback duration, external URLs, browser history, route names, raw player errors, response bodies, device serial numbers, raw exceptions, or stack traces.

### Tutorial Allowed Values

Tutorial-specific enum values (see `analytics_schema/tutorial.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `tutorial_id` | `full`, `overview`, `ai`, `wear_glasses`, `control_music`, `capture`, `call`, `memory`, `translate`, `reminder`, `quick_notes`, `recording_notes`, `voice_commands`, `power`, `unknown` |
| `tutorial_category` | `onboarding`, `device`, `memo_ai`, `unknown` |
| `help_type` | `voice_commands`, `tutorial`, `unknown` |
| `failure_reason` | `user_cancelled`, plus shared values such as `network_error`, `permission_denied`, `validation_failed`, `timeout`, `unsupported_state`, `sdk_error`, `file_missing`, `decode_error`, and `unknown` |

`entry_point`, `surface`, and `trigger_source` follow the approved per-event enum values in `analytics_schema/tutorial.yaml`. Android implementation should add a typed `AnalyticsSurface.TUTORIAL` value, avoid splitting surfaces into `tutorial_center` / `tutorial_media` / `tutorial_help`, and map first-run device-triggered presentation as `entry_point=device` with `trigger_source=system`, not `trigger_source=device`.

### Tutorial Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Open Home and scroll to the Tutorials section; confirm `tutorial_center_viewed` appears once for the visible selected category.
- Switch between Device and Memo AI tutorial tabs and confirm category exposure is not over-counted within one screen presentation.
- Tap several Home tutorial cards and confirm `tutorial_card_opened` carries the correct `tutorial_id` and `tutorial_category`.
- Trigger the first-run Full tutorial after device setup and confirm `tutorial_flow_started` appears once with `tutorial_id=full`, `tutorial_category=onboarding`, and `trigger_source=system`.
- Complete first-run and Home card tutorial flows and confirm `tutorial_flow_completed` appears after the matching `tutorial_flow_started`.
- Close the first-run Full tutorial through the exit dialog and close a Home card tutorial before completion; confirm `tutorial_flow_interrupted` appears with `failure_reason=user_cancelled`.
- Simulate a controlled action failure such as Memo AI enable failure and confirm `tutorial_flow_interrupted` uses an approved non-PII `failure_reason`.
- Tap the Voice Commands help link inside the Tutorial screen and confirm `tutorial_help_link_opened` appears once with `help_type=voice_commands`.
- Simulate an invalid or unsupported tutorial-owned help link and confirm `tutorial_help_link_open_failed`; confirm `tutorial_help_link_opened` is not emitted for the same failed attempt.
- Confirm all tutorial events route through the Android analytics tracker/adapter and no event contains tutorial copy, card titles, localized text, media URLs, thumbnails, file names, playback position, exact duration, full external URLs, browser errors, route names, device serial numbers, raw exceptions, or stack traces.

### Tutorial iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same v1 tutorial event set as Android: `tutorial_center_viewed`, `tutorial_card_opened`, `tutorial_flow_started`, `tutorial_flow_completed`, `tutorial_flow_interrupted`, `tutorial_help_link_opened`, and `tutorial_help_link_open_failed`.
- Confirm iOS uses the same event names, required properties, optional properties, enum values, and trigger boundaries as Android.
- Confirm GA4 can split shared tutorial events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm iOS maps user cancellation, action failure, and help-link open failure to the same `failure_reason` values as Android.
- Confirm all tutorial events route through the iOS analytics facade/adapter and no event contains tutorial copy, card titles, localized text, media URLs, thumbnails, file names, playback position, exact duration, full external URLs, browser errors, route names, device serial numbers, raw exceptions, or stack traces.

### Tutorial Report Usage

- Tutorial discovery: `tutorial_center_viewed` by `tutorial_category`, `platform`, `environment`, and `build_region`.
- Card distribution: `tutorial_card_opened` by `tutorial_id`, `tutorial_category`, and `platform`.
- Tutorial flow funnel: `tutorial_flow_started` -> `tutorial_flow_completed` or `tutorial_flow_interrupted`, split by `tutorial_id`, `tutorial_category`, and `entry_point`.
- First-run tutorial funnel: `tutorial_flow_started` with `tutorial_id=full` -> `tutorial_flow_completed` or `tutorial_flow_interrupted`.
- Interruption breakdown: `tutorial_flow_interrupted` by `failure_reason`, `tutorial_id`, `tutorial_category`, and `platform`.
- Help link reliability: `tutorial_help_link_opened` or `tutorial_help_link_open_failed`, split by `help_type`, `tutorial_id`, and `platform`.

## Translation Production Slice

The Translation slice covers configuration entry, mode/language selection, formal session start/completion/failure, pre-session blocking, and history usage. All v1 events below are defined in `analytics_schema/translation.yaml`.

This slice intentionally excludes raw audio-source analytics, test-build microphone/file/debug recording diagnostics, manual `screen_view`, and membership prompt clicks. Formal Translation audio source is glasses audio. Credits prompts and upgrade clicks remain owned by the global membership/credits event family; Translation keeps only module context through `translation_blocked` and `translation_session_completed`.

| Event | Owner | Platforms | Trigger | Required Properties |
| --- | --- | --- | --- | --- |
| `translation_entry_viewed` | translation | Android+iOS | User enters the Translation configuration page and sees mode, language, and start controls | `entry_point`, `surface` |
| `translation_mode_selected` | translation | Android+iOS | User actively switches Translation mode and the new mode becomes effective | `mode`, `surface` |
| `translation_language_selected` | translation | Android+iOS | User confirms a new language and it is written back to the current Translation configuration | `language_role`, `mode`, `surface` |
| `translation_session_started` | translation | Android+iOS | Client receives `session_ready` and moves from loading into active in-session state | `mode`, `entry_point`, `surface` |
| `translation_blocked` | translation | Android+iOS | User starts Translation or opens from shortcut, but a precondition blocks entry before `session_ready` | `block_reason`, `mode`, `surface` |
| `translation_session_completed` | translation | Android+iOS | A session that reached `session_ready` receives `session_end` and ends normally | `mode`, `session_end_reason`, `surface` |
| `translation_session_failed` | translation | Android+iOS | Session loading fails before active state or an active session ends through an unrecoverable error | `failure_reason`, `mode`, `surface` |
| `translation_history_viewed` | translation | Android+iOS | User enters the Translation History list page | `entry_point`, `surface` |
| `translation_history_opened` | translation | Android+iOS | User opens one Translation history record from the list | `surface`, `record_mode` |
| `translation_history_deleted` | translation | Android+iOS | User confirms deletion for one or more Translation history records and the delete operation is accepted | `delete_mode`, `surface` |

### Translation Deferred Events

| Deferred Event | Reason | Promotion Condition |
| --- | --- | --- |
| Translation audio-source selection | Formal source is fixed to glasses audio; test microphone/file/debug recording belongs to diagnostics. | Add a real user-facing production source selector. |
| Manual `screen_view` | Firebase automatic screen collection remains preferred. | Add only if Translation configuration, language, or history screen semantics are unstable in GA4. |
| Membership prompt shown/clicked | Owned by global membership/credits analytics. | Promote only through the membership/credits plan, not Translation. |
| Reading controls such as font size or source-text toggle | Below v1 critical-path priority. | Add when product needs reading-control analysis. |

### Translation GA4 Custom Definitions

Recommended event-scoped custom dimensions:

| Parameter | Priority | Reason |
| --- | --- | --- |
| `platform` | Shared P0 | Compare Android and iOS Translation behavior in one GA4 property |
| `environment` | Shared P0 | Separate test and production traffic |
| `build_region` | Shared P0 | Support regional analysis from adapter-injected metadata |
| `mode` | P0 | Split Conversation and Listening funnels |
| `entry_point` | P0 | Compare Home, status, shortcut, and voice-command entry paths |
| `surface` | P0 | Split configuration, session, language, and history surfaces |
| `block_reason` | P0 | Explain pre-session blocking |
| `failure_reason` | P0 | Explain session loading and in-session failures |
| `session_end_reason` | P0 | Split normal end and credits-exhausted terminal states |
| `language_role` | P1 | Split Your Language and Their Language selection |
| `language_code` | P1 | Analyze selected stable language codes without search text or labels |
| `selection_method` | P1 | Compare grouped list, search, recent, and memory selection paths |
| `error_scope` | P1 | Split loading, session, paragraph, RTC, DataStream, and network failures |
| `recoverable` | P1 | Split recoverable and unrecoverable failure classes |
| `had_results` | P1 | Distinguish completed sessions with visible results |
| `record_mode` | P1 | Split Conversation and Listening history records |
| `delete_mode` | P1 | Split single and bulk deletion |
| `record_count_bucket` | P1 | Bucket bulk deletion size without record ids |

Do not upload raw audio, original text, translated text, transcript text, free-text search terms, history body, record ids, RTC tokens, channel names, protocol payloads, request ids, response bodies, raw errors, stack traces, permission dialog text, or system error text.

### Translation Allowed Values

Translation-specific enum values (see `analytics_schema/translation.yaml` for per-event scope):

| Property | Allowed Values |
| --- | --- |
| `mode` | `conversation`, `listening`, `unknown` |
| `entry_point` | `home_translate_card`, `home_translating_status`, `glasses_shortcut`, `voice_command`, `translation_config`, `translation_session`, `translation_history`, `unknown` |
| `surface` | `translation_config`, `translation_language`, `translation_session`, `translation_history`, `translation_history_detail`, `home`, `unknown` |
| `trigger_source` | `user`, `system`, `device`, `voice_command`, `unknown` |
| `language_role` | `your_language`, `their_language`, `unknown` |
| `selection_method` | `grouped_list`, `search`, `recent`, `memory`, `unknown` |
| `recognition_policy` | `glasses_audio`, `unknown` |
| `block_reason` | `their_language_missing`, `same_language_pair`, `saved_config_missing`, `glasses_not_connected`, `credits_used_up`, `unknown` |
| `session_end_reason` | `session_end`, `user_ended`, `credits_exhausted`, `unknown` |
| `failure_reason` | `session_init_failed`, `session_ready_timeout`, `session_config_invalid`, `session_already_ended`, `session_idle_timeout`, `paragraph_asr_failed`, `paragraph_out_of_order`, `paragraph_invalid_state`, `translation_failed`, `target_language_unsupported`, `language_detection_failed`, `rtc_join_failed`, `network_error`, `unknown` |
| `error_scope` | `loading`, `session`, `paragraph`, `rtc`, `datastream`, `network`, `unknown` |
| `record_mode` | `conversation`, `listening`, `mixed`, `unknown` |
| `delete_mode` | `single`, `bulk`, `unknown` |
| `record_count_bucket` | `one`, `two_to_five`, `six_to_twenty`, `more_than_twenty`, `unknown` |

Boolean-like params such as `has_history`, `had_results`, and `recoverable` use `true` / `false`.

### Translation Android Verification Checklist

- Enable GA4 DebugView for the Android app stream.
- Enter Translation from Home, active translating status, glasses shortcut, and voice command where supported; confirm `translation_entry_viewed` uses approved `entry_point` and does not over-count one screen presentation.
- Switch between Conversation and Listening; confirm `translation_mode_selected` fires only after the mode is applied.
- Select Your Language and Their Language through grouped list and search; confirm `translation_language_selected` fires only after confirmation and does not include search text or localized labels.
- Start Translation and confirm `translation_session_started` fires only after `session_ready`, not on button tap or loading start.
- Simulate missing target language, same language pair, missing saved config, disconnected glasses, and credits used up; confirm `translation_blocked` fires without `translation_session_started` for the same attempt.
- Complete a session and confirm `translation_session_completed` fires after `session_end`; use `session_end_reason=credits_exhausted` only for stable credit-exhausted terminal sessions.
- Simulate init failure, `session_ready` timeout, RTC join failure, network error, and translation failure; confirm `translation_session_failed` does not also emit `translation_session_completed` for the same attempt.
- Open, inspect, and delete Translation history records; confirm history events never contain record ids, titles, preview text, source text, translated text, transcript text, timestamps, or history body.
- Confirm all Translation events route through the Android analytics tracker/adapter and do not change existing business control flow.

### Translation iOS Verification Checklist

- Enable GA4 DebugView for the iOS app stream.
- Verify the same v1 Translation event set as Android: `translation_entry_viewed`, `translation_mode_selected`, `translation_language_selected`, `translation_session_started`, `translation_blocked`, `translation_session_completed`, `translation_session_failed`, `translation_history_viewed`, `translation_history_opened`, and `translation_history_deleted`.
- Confirm iOS uses the same event names, required properties, optional properties, enum values, and trigger boundaries as Android.
- Confirm GA4 can split shared Translation events by `platform=android` and `platform=ios` without platform-specific event names.
- Confirm iOS maps block and failure reasons to the same stable enum values as Android.
- Confirm all Translation events route through the iOS analytics facade/adapter and no event contains raw audio, source text, translated text, transcript text, search text, history body, ids, tokens, protocol payloads, raw errors, response bodies, or stack traces.

### Translation Report Usage

- Entry-to-session funnel: `translation_entry_viewed` -> `translation_session_started`, split by `entry_point`, `mode`, `platform`, `environment`, and `build_region`.
- Mode and language setup: `translation_mode_selected` and `translation_language_selected`, split by `mode`, `language_role`, `language_code`, and `selection_method`.
- Blocked start breakdown: `translation_blocked` by `block_reason`, `mode`, `entry_point`, and `platform`.
- Session outcome funnel: `translation_session_started` -> `translation_session_completed` or `translation_session_failed`, split by `mode`, `session_end_reason`, `failure_reason`, `error_scope`, and `platform`.
- History usage: `translation_history_viewed` -> `translation_history_opened` or `translation_history_deleted`, split by `record_mode`, `delete_mode`, `record_count_bucket`, and `platform`.

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
| `tutorial_` | First-run tutorial, tutorial center, tutorial media, help links |
| `translation_` | Translation setup, session lifecycle, blocking, history |

Existing canonical event names should not be renamed only for prefix consistency. Rename or migrate events through an explicit Tracking Plan change.

`contact_us_*` is an approved canonical exception for the App Support Contact us flow. Keep it aligned with `analytics_schema/app_support.yaml` unless a future Tracking Plan change explicitly migrates the event family.

`app_login_*` is a deprecated first-slice App-health naming exception. Future login and account-usable-state instrumentation should use `account_login_*` from `analytics_schema/account.yaml`, and implementations must not double-send old and new login events for the same behavior.

## Privacy Guardrails

Do not collect:

- Email, phone, nickname, or chat identifiers.
- Chat content, note content, transcript text, reminder text, file names, or attachment names.
- Precise location, device serial number, tokens, secrets, raw URLs, stack traces, or raw exception messages.
- High-cardinality free text values.

Prefer low-cardinality enums, booleans, counts, durations, and coarse buckets.
