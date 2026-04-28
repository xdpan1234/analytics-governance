# Analytics Provider POC Playbook

This playbook captures the reusable POC pattern from the GA4, Amplitude, Sensors Analytics, PostHog, and Mixpanel evaluations.

## Scope

Provider POCs are for manual feasibility checks:

- SDK initialization.
- Event and property visibility.
- User/profile property visibility.
- Batch or queued upload behavior.
- Offline or weak-network retry observations.
- Backend analysis capability such as funnels, retention, paths, event properties, and reports.

POCs must not change production instrumentation or real business flows.

## Shared Manual Events

Use the same event set across providers:

- `app_boot_completed`
- `login_completed`
- `device_binding_completed`
- `voice_chat_completed`
- `media_import_completed`
- `note_import_completed`
- `reminder_alert_triggered`

Common properties:

| Property | Value |
| --- | --- |
| `platform` | `android` or `ios` |
| `build_region` | `CN` for the CN test package |
| `environment` | `test` |
| `poc_source` | `cn_test_debug` |
| `sample_result` | `success` or `failure` |
| `failure_reason` | `network_unavailable` for the fixed failure sample |

Failure sample:

```text
event_name = voice_chat_completed
sample_result = failure
failure_reason = network_unavailable
```

## Provider Matrix

| Provider | SDK behavior tested | Notes |
| --- | --- | --- |
| GA4/Firebase | Manual `logEvent`, DebugView, internal SDK batching | No public Android flush or batch-size control |
| Amplitude | Manual `track`, `Identify`, `flush`, configurable queue size/interval | Disable autocapture for comparable POC events |
| Sensors Analytics | Manual `track`, `profileSet`, `flush`, local cache behavior | Do not enable auto track, heat map, visualized auto track, or login in the POC |
| PostHog | Manual `capture`, `flush`, queue/batch config, offline queue | Disable lifecycle/screen/deep-link/feature flag/replay defaults unless explicitly testing them |
| Mixpanel | Manual `track`, super properties, `flush`, batch config | Avoid People profile for PII-light tests |

## Credential Rules

Credentials are local-only inputs. Do not commit real values.

| Provider | Local input |
| --- | --- |
| Amplitude | `AMPLITUDE_API_KEY` or `-PamplitudeApiKey` |
| Sensors Analytics | `SENSORS_SERVER_URL` or `-PsensorsServerUrl` |
| PostHog | `POSTHOG_API_KEY`, `POSTHOG_HOST`, `-PposthogApiKey`, `-PposthogHost` |
| Mixpanel | `MIXPANEL_PROJECT_TOKEN` or `-PmixpanelProjectToken` |

Empty credentials should still build successfully. The POC screen should show a missing-credential message and disable send buttons.

## Batch Probe

When testing batching, send 25 `analytics_batch_probe` events with:

- `platform`
- `build_region`
- `environment`
- `poc_source`
- `batch_id`
- `batch_index`
- `batch_size`
- `batch_mode=sdk_batch`
- `provider`

Provider behavior:

- GA4: loop `logEvent`; observe DebugView or later reports. Document that batching is internal and not manually flushable.
- Amplitude: set queue size to 10, send 25 events, then call `flush()`.
- PostHog: set `flushAt=10`, `maxBatchSize=10`, send 25 events, then call `flush()`.
- Mixpanel: configure debug/test batch metadata where available, send 25 events, then call `flush()`.

For offline testing, disable network, send batch, restore network, restart app if needed, and verify whether queued events arrive.

## Event Time Notes

Batch upload does not mean all events share one event time. SDKs typically assign event time when the app records the event, while ingestion time is when the backend receives it.

For offline experiments, add non-sensitive comparison fields when useful:

- `event_occurred_at_ms`
- `batch_created_at_ms`

Use these to compare business event time, SDK event time, and backend ingestion time.

## Manual Validation Checklist

- Build and install the internal test package.
- Open the debug POC page.
- Send each P0 event and the fixed failure sample.
- Confirm event names and properties in provider backend.
- Confirm profile/user properties only contain non-sensitive test fields.
- Send batch probe and confirm 25 events under the same `batch_id`.
- For weak-network checks, confirm whether queued events eventually upload.
- Record provider-specific caveats and redact credentials from docs.
