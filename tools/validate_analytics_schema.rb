#!/usr/bin/env ruby

require "set"
require "yaml"

class AnalyticsSchemaValidator
  REQUIRED_COMMON_PARAMS = %w[
    platform
    environment
    build_region
    build_type
    app_version_name
    app_version_code
  ].freeze

  REQUIRED_CONTRACT_FIELDS = %w[
    android_contract_layer
    android_tracker
    android_event_type
    android_event_spec_type
    android_provider_adapter
    android_direct_sdk_boundary
    ios_contract_layer
    ios_provider_adapter
    ios_direct_sdk_boundary
    required_tests
  ].freeze

  REQUIRED_TESTS = %w[
    ga4_event_name_rules
    ga4_param_name_rules
    ga4_param_count_limit
    reserved_prefix_guardrails
    privacy_field_guardrails
    reporter_output_contract
  ].freeze

  REQUIRED_EVENT_FIELDS = %w[
    event_name
    goal
    recommended_or_custom
    key_event
    trigger_android
    trigger_ios
    required_properties
    optional_properties
    allowed_values
    privacy_notes
    ga4_custom_definitions
    dashboard_usage
    verification_android
    verification_ios
  ].freeze

  APPROVED_OWNER_PREFIXES = {
    "app" => ["app_"],
    "account" => ["account_"],
    "device" => ["device_"],
    "chat" => ["chat_"],
    "media" => ["media_"],
    "note" => ["note_"],
    "reminder" => ["reminder_"],
    "tutorial" => ["tutorial_"],
    "translation" => ["translation_"]
  }.freeze

  EVENT_PREFIX_EXCEPTIONS = {
    "app" => ["contact_us_"]
  }.freeze

  RESERVED_PREFIXES = %w[firebase_ google_ ga_].freeze
  RESERVED_STARTS = ["_", "gtag."].freeze

  PRIVACY_FORBIDDEN_FIELDS = %w[
    email
    phone
    nickname
    url
    full_url
    token
    log_path
    raw_error
    stack_trace
    request_id
    response_body
    file_name
    attachment_name
    precise_location
    device_serial
    serial_number
    raw_locale
    language_candidate_list
  ].freeze

  attr_reader :errors, :event_count

  def initialize(files)
    @files = files
    @errors = []
    @event_count = 0
    @seen_events = {}
  end

  def validate
    @files.each { |file| validate_file(file) }
    errors.empty?
  end

  private

  def validate_file(file)
    data = load_yaml(file)
    return unless data

    unless data.is_a?(Hash)
      add_error(file, nil, "$", "schema root must be a mapping")
      return
    end

    validate_root(file, data)
    events = data["events"]
    return unless events.is_a?(Array)

    common_params = Array(dig(data, "common_properties", "injected_by_adapter")).map(&:to_s)
    owner = data["owner"].to_s
    events.each_with_index do |event, index|
      validate_event(file, event, index, owner, common_params)
    end
  end

  def load_yaml(file)
    YAML.safe_load(File.read(file), permitted_classes: [], permitted_symbols: [], aliases: true)
  rescue Psych::SyntaxError => error
    add_error(file, nil, "$", "invalid YAML: #{error.message}")
    nil
  rescue Errno::ENOENT
    add_error(file, nil, "$", "file does not exist")
    nil
  end

  def validate_root(file, data)
    require_value(file, nil, data, "schema_version")
    add_error(file, nil, "schema_version", "must be 2") unless data["schema_version"] == 2

    owner = data["owner"]
    require_value(file, nil, data, "owner")
    unless APPROVED_OWNER_PREFIXES.key?(owner.to_s)
      add_error(file, nil, "owner", "must be one of #{APPROVED_OWNER_PREFIXES.keys.join(", ")}")
    end

    platforms = data["platforms"]
    require_array(file, nil, data, "platforms")
    if platforms.is_a?(Array)
      invalid = platforms.map(&:to_s) - %w[android ios]
      add_error(file, nil, "platforms", "contains unsupported platform(s): #{invalid.join(", ")}") unless invalid.empty?
    end

    common = data["common_properties"]
    unless common.is_a?(Hash)
      add_error(file, nil, "common_properties", "must be a mapping")
    else
      validate_common_properties(file, common)
    end

    contract = data["implementation_contract"]
    unless contract.is_a?(Hash)
      add_error(file, nil, "implementation_contract", "must be a mapping")
    else
      validate_contract(file, contract)
    end

    events = data["events"]
    require_array(file, nil, data, "events")
    add_error(file, nil, "events", "must not be empty") if events.is_a?(Array) && events.empty?
  end

  def validate_common_properties(file, common)
    injected = common["injected_by_adapter"]
    require_array(file, nil, common, "common_properties.injected_by_adapter", actual_key: "injected_by_adapter")
    if injected.is_a?(Array)
      missing = REQUIRED_COMMON_PARAMS - injected.map(&:to_s)
      unless missing.empty?
        add_error(file, nil, "common_properties.injected_by_adapter", "missing required common param(s): #{missing.join(", ")}")
      end
      injected.each_with_index do |param, index|
        validate_param_name(file, nil, "common_properties.injected_by_adapter[#{index}]", param.to_s)
      end
    end

    definitions = common["definitions"]
    unless definitions.is_a?(Hash)
      add_error(file, nil, "common_properties.definitions", "must be a mapping")
      return
    end

    REQUIRED_COMMON_PARAMS.each do |param|
      require_value(file, nil, definitions, "common_properties.definitions.#{param}", actual_key: param)
    end
  end

  def validate_contract(file, contract)
    REQUIRED_CONTRACT_FIELDS.each do |field|
      if field == "required_tests"
        require_array(file, nil, contract, "implementation_contract.required_tests", actual_key: field)
      else
        require_value(file, nil, contract, "implementation_contract.#{field}", actual_key: field)
      end
    end

    tests = contract["required_tests"]
    return unless tests.is_a?(Array)

    missing = REQUIRED_TESTS - tests.map(&:to_s)
    unless missing.empty?
      add_error(file, nil, "implementation_contract.required_tests", "missing required test(s): #{missing.join(", ")}")
    end
  end

  def validate_event(file, event, index, owner, common_params)
    path = "events[#{index}]"
    unless event.is_a?(Hash)
      add_error(file, nil, path, "must be a mapping")
      return
    end

    event_name = event["event_name"].to_s
    REQUIRED_EVENT_FIELDS.each do |field|
      case field
      when "required_properties", "optional_properties", "ga4_custom_definitions", "dashboard_usage", "verification_android", "verification_ios"
        require_array(file, event_name, event, "#{path}.#{field}", actual_key: field)
      when "allowed_values"
        add_error(file, event_name, "#{path}.allowed_values", "must be a mapping") unless event["allowed_values"].is_a?(Hash)
      when "key_event"
        add_error(file, event_name, "#{path}.key_event", "must be true or false") unless boolean?(event[field])
      else
        require_value(file, event_name, event, "#{path}.#{field}", actual_key: field)
      end
    end

    validate_event_name(file, event_name, path, owner)
    validate_duplicate_event_name(file, event_name) unless event_name.empty?

    required_params = Array(event["required_properties"]).map(&:to_s)
    optional_params = Array(event["optional_properties"]).map(&:to_s)
    event_params = required_params + optional_params

    validate_param_list(file, event_name, "#{path}.required_properties", required_params)
    validate_param_list(file, event_name, "#{path}.optional_properties", optional_params)
    validate_duplicate_params(file, event_name, path, event_params)
    validate_param_count(file, event_name, path, common_params, event_params)
    validate_allowed_values(file, event_name, path, event, event_params)
    validate_custom_definitions(file, event_name, path, event, common_params, event_params)
    validate_custom_metrics(file, event_name, path, event, event_params)

    @event_count += 1
  end

  def validate_event_name(file, event_name, path, owner)
    validate_ga4_name(file, event_name, "#{path}.event_name", event_name)
    return if event_name.empty?

    allowed_prefixes = APPROVED_OWNER_PREFIXES.fetch(owner.to_s, []) + EVENT_PREFIX_EXCEPTIONS.fetch(owner.to_s, [])
    return if allowed_prefixes.any? { |prefix| event_name.start_with?(prefix) }

    add_error(file, event_name, "#{path}.event_name", "must start with #{allowed_prefixes.join(" or ")}")
  end

  def validate_duplicate_event_name(file, event_name)
    previous = @seen_events[event_name]
    if previous
      add_error(file, event_name, "event_name", "Duplicate event_name #{event_name}; first defined in #{previous}")
    else
      @seen_events[event_name] = file
    end
  end

  def validate_param_list(file, event_name, path, params)
    params.each_with_index do |param, index|
      validate_param_name(file, event_name, "#{path}[#{index}]", param)
      if PRIVACY_FORBIDDEN_FIELDS.include?(param)
        add_error(file, event_name, "#{path}[#{index}]", "privacy-forbidden field #{param}")
      end
    end
  end

  def validate_duplicate_params(file, event_name, path, params)
    duplicates = params.group_by { |param| param }.select { |_param, values| values.size > 1 }.keys
    return if duplicates.empty?

    add_error(file, event_name, path, "duplicate param(s): #{duplicates.join(", ")}")
  end

  def validate_param_count(file, event_name, path, common_params, event_params)
    total = (common_params + event_params).uniq.size
    return if total <= 25

    add_error(file, event_name, path, "has #{total} params including common params; GA4 limit is 25")
  end

  def validate_allowed_values(file, event_name, path, event, event_params)
    allowed_values = event["allowed_values"]
    return unless allowed_values.is_a?(Hash)

    allowed_values.each do |param, values|
      param_name = param.to_s
      unless event_params.include?(param_name)
        add_error(file, event_name, "#{path}.allowed_values.#{param_name}", "references unknown event param")
      end
      unless values.is_a?(Array)
        add_error(file, event_name, "#{path}.allowed_values.#{param_name}", "must be a list")
      end
    end
  end

  def validate_custom_definitions(file, event_name, path, event, common_params, event_params)
    definitions = event["ga4_custom_definitions"]
    return unless definitions.is_a?(Array)

    known_params = common_params + event_params
    definitions.each_with_index do |definition, index|
      definition_name = definition.to_s
      validate_param_name(file, event_name, "#{path}.ga4_custom_definitions[#{index}]", definition_name)
      unless known_params.include?(definition_name)
        add_error(file, event_name, "#{path}.ga4_custom_definitions[#{index}]", "references unknown param #{definition_name}")
      end
    end
  end

  def validate_custom_metrics(file, event_name, path, event, event_params)
    metrics = event["ga4_custom_metrics"]
    return if metrics.nil?

    unless metrics.is_a?(Array)
      add_error(file, event_name, "#{path}.ga4_custom_metrics", "must be a list")
      return
    end

    metrics.each_with_index do |metric, index|
      metric_name = metric.to_s
      validate_param_name(file, event_name, "#{path}.ga4_custom_metrics[#{index}]", metric_name)
      unless event_params.include?(metric_name)
        add_error(file, event_name, "#{path}.ga4_custom_metrics[#{index}]", "references unknown event param #{metric_name}")
      end
    end
  end

  def validate_param_name(file, event_name, path, name)
    validate_ga4_name(file, event_name, path, name)
  end

  def validate_ga4_name(file, event_name, path, name)
    if name.nil? || name.empty?
      add_error(file, event_name, path, "must not be empty")
      return
    end

    unless name.match?(/\A[a-z][a-z0-9_]{0,39}\z/)
      add_error(file, event_name, path, "must be lower snake case, start with a letter, and be <= 40 chars")
    end

    if RESERVED_PREFIXES.any? { |prefix| name.start_with?(prefix) }
      add_error(file, event_name, path, "must not use reserved prefix firebase_, google_, or ga_")
    end

    if RESERVED_STARTS.any? { |prefix| name.start_with?(prefix) }
      add_error(file, event_name, path, "must not start with _, gtag., or another reserved start")
    end
  end

  def require_value(file, event_name, object, path, actual_key: nil)
    key = actual_key || path
    value = object[key]
    return unless value.nil? || (value.respond_to?(:empty?) && value.empty?)

    add_error(file, event_name, path, "is required")
  end

  def require_array(file, event_name, object, path, actual_key: nil)
    key = actual_key || path
    value = object[key]
    unless value.is_a?(Array)
      add_error(file, event_name, path, "must be a list")
    end
  end

  def dig(object, *keys)
    keys.reduce(object) do |current, key|
      current.is_a?(Hash) ? current[key] : nil
    end
  end

  def boolean?(value)
    value == true || value == false
  end

  def add_error(file, event_name, path, message)
    event_label = event_name.nil? || event_name.empty? ? "-" : event_name
    @errors << "#{file}:#{event_label}:#{path} #{message}"
  end
end

def default_schema_files
  root = File.expand_path("..", __dir__)
  Dir[File.join(root, "analytics_schema", "*.yaml")].sort
end

if $PROGRAM_NAME == __FILE__
  files = ARGV.empty? ? default_schema_files : ARGV
  validator = AnalyticsSchemaValidator.new(files)

  if validator.validate
    puts "Validated #{files.size} file(s), #{validator.event_count} event(s)."
    exit 0
  end

  warn validator.errors.join("\n")
  exit 1
end
