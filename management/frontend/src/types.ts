export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface Meta { scope: string; read_only: true; mode: 'FROZEN_REPLAY'; dispatch_enabled: false; notifications_sent: 0 }
export interface RunSummary {
  run_id: string; target_day: string; data_status: string; process_status: string
  created_at: string; reports: number; accounts: number; findings: number
}
export interface Funnel { observed_accounts: number; eligible_accounts: number; matched_accounts: number; proposed_accounts: number }
export interface RunDetail {
  run_id: string; target_day: string; data_status: string; process_status: string; snapshot_id: string
  source_sha256: string; implementation_sha256: string; rules_version: string
  candidate_summary: { statistical_days: string[]; funnel: Funnel; [key: string]: unknown }
  policy: unknown; provenance: unknown; archive_manifest: unknown; source_manifest: unknown; day_coverage: unknown
  report_days: string[]; executions: { execution_id: string; namespace: string; flow_id: string }[]
}
export interface ComparisonMetric {
  current: number | null; reference: number | null; delta: number | null; relative_change: number | null
  status: string; change_status: string; reference_days: number; expected_reference_days: number
  delta_percentage_points?: number | null; unavailable_reason: string | null
}
export type Comparison = Record<'records' | 'identified_accounts' | 'result_rate', ComparisonMetric>
export interface EventMetric {
  event_name: string; records: number; identified_accounts: number; result_rate: number | null; result_rate_status: string
  previous_day_comparison: Comparison; baseline_comparison: Comparison; [key: string]: unknown
}
export interface ReportContent {
  statistical_day: string; top10: EventMetric[]; events: EventMetric[]
  baseline_summary: { method: string; available_days: number; expected_days: number; status: string; missing_days: string[] }
  quality: { status: string; [key: string]: unknown }; table_coverage: unknown; window: unknown
}
export interface ReportReply { statistical_day: string; content: ReportContent }
export interface Proposal {
  account_id: string; platform: string; statistical_day: string; app_versions: string[]; records: number
  matched_rules: string[]; priority_reason: string; evidence: { event_name: string; failure_reason: string | null }
  selection: { reason: string; order: number | null }; [key: string]: unknown
}
export interface UserSummary {
  account_id: string; run_id: string; context_id: string; selection_order: number; selection_outcome: string; target_state: string
  proposal: Proposal; findings: number; facts: number; target_day: string; imported_at: string
}
export interface Finding {
  finding_id: string; event_name: string; reason: string | null; statistical_day: string; platform: string
  account_records: number; group_accounts: number; matched_rules: string[]; evidence_fact_ids: string[]
  selection: { reason: string }; population_comparison: unknown
  investigation: { status: string; confidence: string; suspected_area: string; checks: string[]; search_terms: string[] }
}
export interface Observation {
  fact_id: string; source_row_sha256: string; event_name: string; statistical_day: string; platform: string
  app_version: string | null; records: number; reason: string | null; first_event_at: string; last_event_at: string
  parameter_status: string; reason_status: string | null
}
export interface Exclusion {
  account_id?: string | null; statistical_day: string; event_name: string; platform: string; records: number
  reason: string; last_event_at: string
}
export interface DiagnosticContent {
  account_id: string; run_id: string; observations: Observation[]; findings: Finding[]; exclusions: Exclusion[]; limitations: string[]
}
export interface Context {
  account_id: string; run_id: string; context_id: string; selection_order: number; selection_outcome: string; target_state: string
  proposal: Proposal; content: DiagnosticContent
}
