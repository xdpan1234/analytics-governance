-- Apply only to the independent analytics_management database as analytics_owner.
CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION analytics_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE TABLE IF NOT EXISTS analytics.telemetry_runs (
    run_id text PRIMARY KEY CHECK (run_id ~ '^[0-9a-f]{64}$'),
    scope_key text NOT NULL,
    mode text NOT NULL CHECK (mode = 'FROZEN_REPLAY'),
    target_day date NOT NULL,
    evaluation_as_of timestamptz NOT NULL,
    snapshot_id text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    rules_version text NOT NULL,
    implementation_sha256 text NOT NULL,
    data_status text NOT NULL CHECK (data_status IN ('WAITING_EXPORT','AVAILABLE','DEGRADED','NO_DATA')),
    process_status text NOT NULL CHECK (process_status = 'SUCCEEDED'),
    ingest_sha256 text NOT NULL CHECK (ingest_sha256 ~ '^[0-9a-f]{64}$'),
    analysis jsonb NOT NULL,
    provenance jsonb NOT NULL,
    archive_manifest jsonb NOT NULL,
    source_manifest jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, scope_key),
    CHECK (analysis->>'dispatch_enabled' = 'false'),
    CHECK (analysis->>'quota_authoritative' = 'false')
);
CREATE INDEX IF NOT EXISTS runs_scope_day ON analytics.telemetry_runs(scope_key, target_day DESC);

CREATE TABLE IF NOT EXISTS analytics.daily_reports (
    report_revision_id text PRIMARY KEY CHECK (report_revision_id ~ '^[0-9a-f]{64}$'),
    run_id text NOT NULL REFERENCES analytics.telemetry_runs(run_id),
    statistical_day date NOT NULL,
    content_sha256 text NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, statistical_day)
);
CREATE TABLE IF NOT EXISTS analytics.diagnostic_contexts (
    context_id text PRIMARY KEY CHECK (context_id ~ '^[0-9a-f]{64}$'),
    run_id text NOT NULL REFERENCES analytics.telemetry_runs(run_id),
    account_id text NOT NULL CHECK (account_id ~ '^[1-9][0-9]*$'),
    target_state text NOT NULL CHECK (target_state = 'UNRESOLVED'),
    selection_outcome text NOT NULL CHECK (selection_outcome = 'SELECTED_PREVIEW'),
    selection_order integer NOT NULL CHECK (selection_order > 0),
    proposal jsonb NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, account_id),
    UNIQUE (run_id, selection_order),
    UNIQUE (run_id, account_id, context_id)
);
CREATE INDEX IF NOT EXISTS contexts_account ON analytics.diagnostic_contexts(account_id, run_id);
CREATE TABLE IF NOT EXISTS analytics.telemetry_findings (
    finding_revision_id text PRIMARY KEY CHECK (finding_revision_id ~ '^[0-9a-f]{64}$'),
    finding_key text NOT NULL CHECK (finding_key ~ '^[0-9a-f]{64}$'),
    run_id text NOT NULL,
    account_id text NOT NULL,
    context_id text NOT NULL,
    statistical_day date NOT NULL,
    platform text NOT NULL,
    event_name text NOT NULL,
    records bigint NOT NULL CHECK (records > 0),
    selection_reason text NOT NULL,
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (run_id, account_id, context_id)
        REFERENCES analytics.diagnostic_contexts(run_id, account_id, context_id),
    UNIQUE (run_id, finding_key)
);
CREATE INDEX IF NOT EXISTS findings_account_run ON analytics.telemetry_findings(account_id, run_id);
CREATE TABLE IF NOT EXISTS analytics.run_executions (
    run_id text NOT NULL REFERENCES analytics.telemetry_runs(run_id),
    execution_id text NOT NULL,
    namespace text NOT NULL,
    flow_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, execution_id)
);

GRANT USAGE ON SCHEMA analytics TO analytics_reader, analytics_importer;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_reader, analytics_importer;
GRANT INSERT ON ALL TABLES IN SCHEMA analytics TO analytics_importer;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO analytics_reader, analytics_importer;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT INSERT ON TABLES TO analytics_importer;
