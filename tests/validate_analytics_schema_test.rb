require "fileutils"
require "minitest/autorun"
require "open3"
require "tmpdir"
require "yaml"

class ValidateAnalyticsSchemaTest < Minitest::Test
  ROOT = File.expand_path("..", __dir__)
  SCRIPT = File.join(ROOT, "tools", "validate_analytics_schema.rb")

  def test_accepts_valid_schema
    Dir.mktmpdir do |dir|
      schema = write_schema(dir, "valid.yaml", valid_schema)

      stdout, stderr, status = run_validator(schema)

      assert status.success?, stderr
      assert_includes stdout, "Validated 1 file(s), 1 event(s)."
    end
  end

  def test_accepts_tutorial_owner_prefix
    Dir.mktmpdir do |dir|
      schema = write_schema(dir, "tutorial.yaml", valid_schema(owner: "tutorial", event_name: "tutorial_test_event"))

      stdout, stderr, status = run_validator(schema)

      assert status.success?, stderr
      assert_includes stdout, "Validated 1 file(s), 1 event(s)."
    end
  end

  def test_accepts_translation_owner_prefix
    Dir.mktmpdir do |dir|
      schema = write_schema(dir, "translation.yaml", valid_schema(owner: "translation", event_name: "translation_test_event"))

      stdout, stderr, status = run_validator(schema)

      assert status.success?, stderr
      assert_includes stdout, "Validated 1 file(s), 1 event(s)."
    end
  end

  def test_rejects_missing_required_schema_and_event_fields
    Dir.mktmpdir do |dir|
      schema = write_schema(dir, "missing.yaml", <<~YAML)
        schema_version: 2
        owner: app
        platforms:
          - android
          - ios
        common_properties:
          injected_by_adapter:
            - platform
          definitions:
            platform: Lowercase client platform.
        implementation_contract: {}
        events:
          - event_name: app_missing_fields
      YAML

      stdout, stderr, status = run_validator(schema)

      refute status.success?
      output = stdout + stderr
      assert_includes output, "common_properties.injected_by_adapter"
      assert_includes output, "implementation_contract.android_contract_layer"
      assert_includes output, "events[0].goal"
    end
  end

  def test_rejects_invalid_ga4_names_and_reserved_prefixes
    Dir.mktmpdir do |dir|
      schema = write_schema(
        dir,
        "invalid_names.yaml",
        valid_schema(
          event_name: "firebase_bad",
          required_properties: ["_bad_param", "GoogleParam"],
          allowed_values: { "_bad_param" => ["ok"], "GoogleParam" => ["ok"] }
        )
      )

      stdout, stderr, status = run_validator(schema)

      refute status.success?
      output = stdout + stderr
      assert_includes output, "events[0].event_name"
      assert_includes output, "events[0].required_properties[0]"
      assert_includes output, "events[0].required_properties[1]"
    end
  end

  def test_rejects_too_many_event_params_including_common_params
    Dir.mktmpdir do |dir|
      params = (1..20).map { |index| "param_#{index}" }
      schema = write_schema(
        dir,
        "too_many_params.yaml",
        valid_schema(
          required_properties: params,
          optional_properties: [],
          allowed_values: params.to_h { |param| [param, ["ok"]] }
        )
      )

      stdout, stderr, status = run_validator(schema)

      refute status.success?
      assert_includes stdout + stderr, "has 26 params including common params"
    end
  end

  def test_rejects_references_to_unknown_params
    Dir.mktmpdir do |dir|
      schema = write_schema(
        dir,
        "unknown_refs.yaml",
        valid_schema(extra_event: {
          "allowed_values" => { "missing_param" => ["ok"] },
          "ga4_custom_definitions" => ["missing_definition"],
          "ga4_custom_metrics" => ["missing_metric"]
        })
      )

      stdout, stderr, status = run_validator(schema)

      refute status.success?
      output = stdout + stderr
      assert_includes output, "allowed_values.missing_param"
      assert_includes output, "ga4_custom_definitions[0]"
      assert_includes output, "ga4_custom_metrics[0]"
    end
  end

  def test_rejects_duplicate_event_names_across_files
    Dir.mktmpdir do |dir|
      first = write_schema(dir, "one.yaml", valid_schema(event_name: "app_duplicate_event"))
      second = write_schema(dir, "two.yaml", valid_schema(event_name: "app_duplicate_event"))

      stdout, stderr, status = run_validator(first, second)

      refute status.success?
      assert_includes stdout + stderr, "Duplicate event_name app_duplicate_event"
    end
  end

  def test_rejects_sensitive_privacy_fields
    Dir.mktmpdir do |dir|
      schema = write_schema(
        dir,
        "sensitive.yaml",
        valid_schema(
          required_properties: ["email"],
          allowed_values: { "email" => ["ok"] }
        )
      )

      stdout, stderr, status = run_validator(schema)

      refute status.success?
      assert_includes stdout + stderr, "privacy-forbidden field email"
    end
  end

  private

  def run_validator(*files)
    Open3.capture3("ruby", SCRIPT, *files)
  end

  def write_schema(dir, name, content)
    path = File.join(dir, name)
    File.write(path, content)
    path
  end

  def valid_schema(
    owner: "app",
    event_name: "app_test_event",
    required_properties: ["entry_point"],
    optional_properties: ["surface"],
    allowed_values: { "entry_point" => ["settings"], "surface" => ["settings"] },
    extra_event: {}
  )
    event = {
      "event_name" => event_name,
      "goal" => "Measure a test event.",
      "recommended_or_custom" => "custom",
      "key_event" => false,
      "trigger_android" => "Android test trigger.",
      "trigger_ios" => "iOS test trigger.",
      "required_properties" => required_properties,
      "optional_properties" => optional_properties,
      "allowed_values" => allowed_values,
      "privacy_notes" => "Do not include email, phone, nickname, raw URLs, tokens, or raw errors.",
      "ga4_custom_definitions" => required_properties + optional_properties + ["platform"],
      "dashboard_usage" => ["test_dashboard"],
      "verification_android" => ["Confirm the event in Android DebugView."],
      "verification_ios" => ["Confirm the event in iOS DebugView."]
    }.merge(extra_event)

    {
      "schema_version" => 2,
      "owner" => owner,
      "platforms" => ["android", "ios"],
      "common_properties" => {
        "injected_by_adapter" => [
          "platform",
          "environment",
          "build_region",
          "build_type",
          "app_version_name",
          "app_version_code"
        ],
        "definitions" => {
          "platform" => "Lowercase client platform.",
          "environment" => "Analytics environment.",
          "build_region" => "Analytics build region.",
          "build_type" => "Client build type.",
          "app_version_name" => "Public app version.",
          "app_version_code" => "Numeric app version."
        }
      },
      "implementation_contract" => {
        "android_contract_layer" => "domain:api:analytics",
        "android_tracker" => "AnalyticsTracker",
        "android_event_type" => "AnalyticsEvent",
        "android_event_spec_type" => "AnalyticsEventSpec",
        "android_provider_adapter" => "Ga4AnalyticsAdapter",
        "android_direct_sdk_boundary" => "Only the app-level provider adapter may call FirebaseAnalytics.",
        "ios_contract_layer" => "iOS analytics facade matching this schema",
        "ios_provider_adapter" => "GA4/Firebase adapter behind the iOS facade",
        "ios_direct_sdk_boundary" => "Only the iOS provider adapter may call Firebase Analytics.logEvent.",
        "required_tests" => [
          "ga4_event_name_rules",
          "ga4_param_name_rules",
          "ga4_param_count_limit",
          "reserved_prefix_guardrails",
          "privacy_field_guardrails",
          "reporter_output_contract"
        ]
      },
      "events" => [event]
    }.to_yaml
  end
end
