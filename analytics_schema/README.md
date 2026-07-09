# Analytics Schema

This directory is the machine-readable contract for shared Android and iOS production analytics events. Keep it aligned with `docs/tracking-plan.md` and the platform typed analytics contracts.

## Schema Version 2

Every active YAML schema must use this top-level shape:

```yaml
schema_version: 2
owner: <app|account|device|media|note|reminder|chat|tutorial|translation>
platforms:
  - android
  - ios
common_properties:
  injected_by_adapter:
    - platform
    - environment
    - build_region
    - build_type
    - app_version_name
    - app_version_code
  definitions:
    platform: Lowercase client platform, such as android or ios.
    environment: Analytics environment, test or prod.
    build_region: Analytics build region. Current Android rule is prod -> us, test -> sg.
    build_type: Client build type such as debug or release.
    app_version_name: Public app version name injected by the client adapter.
    app_version_code: Numeric app version code injected by the client adapter.
implementation_contract:
  android_contract_layer: "domain:api:analytics"
  android_tracker: "AnalyticsTracker"
  android_event_type: "AnalyticsEvent"
  android_event_spec_type: "AnalyticsEventSpec"
  android_provider_adapter: "Ga4AnalyticsAdapter"
  android_direct_sdk_boundary: "Only the app-level provider adapter may call FirebaseAnalytics."
  ios_contract_layer: "iOS analytics facade matching this schema"
  ios_provider_adapter: "GA4/Firebase adapter behind the iOS facade"
  ios_direct_sdk_boundary: "Only the iOS provider adapter may call Firebase Analytics.logEvent."
  required_tests:
    - ga4_event_name_rules
    - ga4_param_name_rules
    - ga4_param_count_limit
    - reserved_prefix_guardrails
    - privacy_field_guardrails
    - reporter_output_contract
events: []
```

## Event Fields

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

Optional numeric analysis metrics go in `ga4_custom_metrics`, for example a future terminal event with `playback_duration_ms`. Do not add a metric unless the event actually sends a numeric parameter intended for GA4 custom metric registration.

## Validator

Run the schema validator before using YAML to generate Android or iOS code:

```bash
ruby tools/validate_analytics_schema.rb
```

To validate one module:

```bash
ruby tools/validate_analytics_schema.rb analytics_schema/app_basic.yaml
```

The validator checks schema v2 required fields, GA4 event and param naming, reserved prefixes, event param count including adapter-injected common params, `allowed_values` references, custom definition and metric references, duplicate event names, privacy-forbidden fields, and the `contact_us_*` event-name exception.

## Implementation Rules

- Update schema before production instrumentation.
- Device usage events use the `device_usage_*` event-name family but remain in `device.yaml` because the owner prefix is `device_`.
- If production app code already contains typed analytics events that are missing here, backfill the matching owner schema and Tracking Plan before further code generation.
- POC-only events stay in `docs/provider-poc-playbook.md` unless promoted into the formal Tracking Plan.
- Business code must use typed reporters or `AnalyticsTracker`; direct Firebase SDK calls belong only in provider adapters.
- Android and iOS must share event names, parameter names, enum values, trigger boundaries, and privacy notes unless a schema explicitly documents a platform difference.
- Common adapter params are not repeated in event `required_properties` or `optional_properties`.
- `user_id` and user properties are managed by tracker/adapter APIs, not ordinary event params.
- For elapsed-time analysis, prefer sending a duration metric on the terminal event, such as `*_duration_ms`, instead of relying on GA4 UI to pair start and end events.

## Code Generation Contract

Use `app_basic.yaml` as the reference shape for App code generation.

Android mapping:

- `events[].event_name` maps to `AnalyticsEventName`.
- `required_properties` and `optional_properties` map to `AnalyticsEventSpec`.
- property names map to `AnalyticsParamName`.
- `allowed_values` maps to typed enums and value mappers.
- trigger boundaries map to module reporter methods such as `AppBasicAnalyticsReporter.reportLegalLinkOpened(...)`.
- common params remain in `AnalyticsCommonParamProvider`.
- Firebase dispatch remains behind `DefaultAnalyticsTracker` and `Ga4AnalyticsAdapter`.

iOS mapping:

- `events[].event_name` maps to `AnalyticsEventName` raw values.
- `required_properties` and `optional_properties` map to `AnalyticsEventSpec`.
- property names map to `AnalyticsParamName`.
- `allowed_values` maps to typed Swift enums.
- trigger boundaries map to module reporter methods such as `AppBasicAnalyticsReporter.reportLegalLinkOpened(...)`.
- common params remain in `AppAnalyticsCommonParamProvider`.
- Firebase dispatch remains behind `DefaultAnalyticsTracker` and `Ga4AnalyticsAdapter`.

## Deprecated Files

`app_login.yaml` has been removed. Login and auth-state restoration are owned by `account.yaml` through the `account_login_*` event family.
