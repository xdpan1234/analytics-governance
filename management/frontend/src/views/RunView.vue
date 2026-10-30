<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { get, query, useLoad } from '../api'
import { label } from '../format'
import type { Page, ReportReply, RunDetail, UserSummary } from '../types'
import AccountSearch from '../components/AccountSearch.vue'
import ArchiveRows from '../components/ArchiveRows.vue'
import LoadState from '../components/LoadState.vue'
import RawData from '../components/RawData.vue'
import ReportPanel from '../components/ReportPanel.vue'
const route = useRoute(), router = useRouter()
const runId = computed(() => String(route.params.run_id))
const account = computed(() => String(route.query.account ?? ''))
const { data, loading, error, reload } = useLoad(() => route.path + JSON.stringify(route.query), async signal => {
  const id = encodeURIComponent(runId.value)
  const run = await get<RunDetail>(`/runs/${id}`, signal)
  const day = String(route.query.day || run.report_days[0] || '')
  const [report, users] = await Promise.all([
    day ? get<ReportReply>(`/runs/${id}/reports/${encodeURIComponent(day)}`, signal) : Promise.resolve(null),
    get<Page<UserSummary>>(`/runs/${id}/users` + query({ account: account.value }), signal),
  ])
  return { run, day, report: report?.content, users }
})
function search(value: string) { router.push({ query: { ...route.query, account: value || undefined } }) }
function changeDay(day: string) { router.push({ query: { ...route.query, day } }) }
function executionUrl(execution: RunDetail['executions'][number]) {
  return `http://127.0.0.1:8080/ui/main/executions/${encodeURIComponent(execution.namespace)}/${encodeURIComponent(execution.flow_id)}/${encodeURIComponent(execution.execution_id)}/outputs`
}
</script>
<template>
  <p class="breadcrumb"><RouterLink to="/">全部批次</RouterLink></p><h1>批次 {{ runId.slice(0, 16) }}</h1>
  <LoadState :loading="loading" :error="error" @retry="reload" />
  <template v-if="data">
    <dl class="stats six">
      <div><dt>请求统计日</dt><dd>{{ data.run.target_day }}</dd></div><div><dt>数据状态</dt><dd>{{ label(data.run.data_status) }}</dd></div>
      <div><dt>观察账号</dt><dd>{{ data.run.candidate_summary.funnel.observed_accounts }}</dd></div>
      <div><dt>合格账号</dt><dd>{{ data.run.candidate_summary.funnel.eligible_accounts }}</dd></div>
      <div><dt>命中账号</dt><dd>{{ data.run.candidate_summary.funnel.matched_accounts }}</dd></div>
      <div><dt>候选预览</dt><dd>{{ data.run.candidate_summary.funnel.proposed_accounts }}</dd></div>
    </dl>
    <p>计算状态：{{ label(data.run.process_status) }}。漏斗统计日：{{ data.run.candidate_summary.statistical_days.join('、') }}；请求日缺表时保留等待导出状态。</p>
    <nav class="day-tabs" aria-label="日报日期"><el-button v-for="day in data.run.report_days" :key="day" :type="day === data.day ? 'primary' : 'default'" :aria-pressed="day === data.day" @click="changeDay(day)">{{ day }}</el-button></nav>
    <ReportPanel v-if="data.report" :report="data.report" />
    <h2>候选用户</h2><AccountSearch :account="account" @search="search" />
    <el-table :data="data.users.items" border empty-text="没有符合条件的候选用户。">
      <el-table-column prop="selection_order" label="顺序" width="70" />
      <el-table-column label="账号" width="105"><template #default="{ row }"><RouterLink :to="{ path: `/users/${row.account_id}`, query: { run: runId } }">{{ row.account_id }}</RouterLink></template></el-table-column>
      <el-table-column label="主线索 / 原因" min-width="285"><template #default="{ row }"><code>{{ row.proposal.evidence.event_name }}</code><small>{{ row.proposal.evidence.failure_reason ?? '未提供' }}</small></template></el-table-column>
      <el-table-column label="平台 / 版本" min-width="135"><template #default="{ row }">{{ row.proposal.platform }}<small>{{ row.proposal.app_versions.join(' / ') }}</small></template></el-table-column>
      <el-table-column label="命中规则" min-width="210"><template #default="{ row }"><small v-for="rule in row.proposal.matched_rules" :key="rule">{{ label(rule) }}</small></template></el-table-column>
      <el-table-column label="线索 / 埋点聚合" min-width="150"><template #default="{ row }">{{ row.findings }} / {{ row.facts }}</template></el-table-column>
    </el-table>
    <h2>筛选与排除</h2>
    <RawData title="各阶段原因统计与固定策略" :value="{ candidate_summary: data.run.candidate_summary, policy: data.run.policy }" />
    <ArchiveRows :run-id="runId" :account="account" kind="candidates" title="完整候选池（含未选中原因）" />
    <ArchiveRows :run-id="runId" :account="account" kind="exclusions" title="全部排除记录（保留原始排除码）" />
    <h2>来源与版本</h2>
    <dl class="metadata"><template v-for="key in (['run_id', 'snapshot_id', 'source_sha256', 'rules_version', 'implementation_sha256'] as const)" :key="key"><dt>{{ key }}</dt><dd class="mono">{{ data.run[key] }}</dd></template></dl>
    <p v-for="execution in data.run.executions" :key="execution.execution_id"><a :href="executionUrl(execution)">查看 Kestra 执行 {{ execution.execution_id }}</a></p>
    <RawData title="源快照清单、归档摘要与数据覆盖" :value="{ provenance: data.run.provenance, archive_manifest: data.run.archive_manifest, source_manifest: data.run.source_manifest, day_coverage: data.run.day_coverage }" />
  </template>
</template>
