<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { get, useLoad } from '../api'
import { label, utc } from '../format'
import type { Context, Page, UserSummary } from '../types'
import AccountSearch from '../components/AccountSearch.vue'
import EvidenceTable from '../components/EvidenceTable.vue'
import LoadState from '../components/LoadState.vue'
import RawData from '../components/RawData.vue'
const route = useRoute(), router = useRouter()
const account = computed(() => String(route.params.account_id || route.query.account || ''))
const { data, loading, error, reload } = useLoad(() => route.path + JSON.stringify(route.query), async signal => {
  if (!account.value) return null
  const history = await get<Page<UserSummary>>(`/users/${encodeURIComponent(account.value)}`, signal)
  if (!history.items.length) return { history, context: null }
  const run = String(route.query.run || history.items[0]!.run_id)
  const context = await get<Context>(`/users/${encodeURIComponent(account.value)}/contexts/${encodeURIComponent(run)}`, signal)
  return { history, context }
})
function search(value: string) { router.push({ path: '/users', query: value ? { account: value } : {} }) }
</script>
<template>
  <h1>{{ account ? `用户 ${account}` : '按用户查询' }}</h1>
  <AccountSearch :account="account" @search="search" />
  <LoadState :loading="loading" :error="error" @retry="reload" />
  <el-empty v-if="!account && !loading" description="输入业务账号 ID，查看已归档批次、筛选原因与埋点证据。" />
  <template v-if="data">
    <el-empty v-if="!data.history.items.length" description="该账号没有已归档候选上下文。当前仅保存预览选中账号的独立上下文；这不代表该账号没有异常。" />
    <template v-else>
      <h2>已归档批次（最近 {{ data.history.limit }} 个）</h2>
      <el-table :data="data.history.items" border>
        <el-table-column prop="target_day" label="请求统计日" min-width="135" />
        <el-table-column label="批次" min-width="220"><template #default="{ row }"><RouterLink :to="{ path: `/users/${account}`, query: { run: row.run_id } }">{{ row.run_id.slice(0, 16) }}</RouterLink></template></el-table-column>
        <el-table-column label="上下文" min-width="220"><template #default="{ row }"><code>{{ row.context_id.slice(0, 16) }}…</code></template></el-table-column>
      </el-table>
    </template>
    <template v-if="data.context">
      <p><RouterLink :to="`/runs/${data.context.run_id}`">返回本批次日报与候选用户</RouterLink></p>
      <dl class="stats four">
        <div><dt>关联线索</dt><dd>{{ data.context.content.findings.length }}</dd></div>
        <div><dt>埋点聚合行</dt><dd>{{ data.context.content.observations.length }}</dd></div>
        <div><dt>目标状态</dt><dd>{{ label(data.context.target_state) }}</dd></div>
        <div><dt>采集任务</dt><dd>0</dd></div>
      </dl>
      <h2>为什么选中该账号</h2>
      <p><el-tag>{{ label(data.context.selection_outcome) }}</el-tag> 顺序 {{ data.context.selection_order }}；主线索统计日 {{ data.context.proposal.statistical_day }}，{{ data.context.proposal.platform }}，{{ data.context.proposal.records }} 条记录。</p>
      <p>命中规则：{{ data.context.proposal.matched_rules.map(label).join('、') }}。优先级依据：{{ label(data.context.proposal.priority_reason) }}。</p>
      <RawData title="完整选样依据、组占比及合并线索" :value="data.context.proposal" />
      <h2>关联线索与问题推断</h2>
      <p class="muted">以下检查方向由规则生成，均为待验证假设；语义搜索词不能直接当作精确日志标签。</p>
      <article v-for="finding in data.context.content.findings" :key="finding.finding_id" class="finding">
        <h3><code>{{ finding.event_name }}</code> · {{ finding.reason ?? '未提供' }}</h3>
        <p>{{ finding.statistical_day }} · {{ finding.platform }} · {{ finding.account_records }} 条 · 组内 {{ finding.group_accounts }} 个账号 <el-tag>{{ label(finding.selection.reason) }}</el-tag></p>
        <p>规则：{{ finding.matched_rules.map(label).join('、') }}。排查方向：{{ finding.investigation.suspected_area }}。</p>
        <ul><li v-for="check in finding.investigation.checks" :key="check">{{ check }}</li></ul>
        <p>语义搜索词：{{ finding.investigation.search_terms.join(' / ') }}</p>
        <p class="fact-links">支持本线索的事实：<RouterLink v-for="id in finding.evidence_fact_ids" :key="id" :to="{ path: route.path, query: route.query, hash: `#fact-${id}` }"><code>{{ id.slice(0, 12) }}</code></RouterLink></p>
        <RawData title="线索身份、全人群比较与证据引用" :value="finding" />
      </article>
      <h2>该账号的排除记录</h2>
      <el-table :data="data.context.content.exclusions" border empty-text="该上下文没有排除记录。">
        <el-table-column prop="statistical_day" label="统计日" width="125" />
        <el-table-column label="事件" min-width="275"><template #default="{ row }"><code>{{ row.event_name }}</code></template></el-table-column>
        <el-table-column prop="platform" label="平台" width="95" /><el-table-column prop="records" label="记录数" width="90" />
        <el-table-column label="排除原因" min-width="180"><template #default="{ row }">{{ label(row.reason) }}</template></el-table-column>
        <el-table-column label="末次事件 UTC" min-width="280"><template #default="{ row }">{{ utc(row.last_event_at) }}</template></el-table-column>
      </el-table>
      <h2>埋点证据</h2>
      <p class="muted">冻结查询范围内的 UTC 日聚合；首末时间是聚合界限。点击线索的事实 ID 可自动切换证据页并定位。</p>
      <EvidenceTable :observations="data.context.content.observations" />
      <h2>诊断上下文</h2><p class="mono">context_id: {{ data.context.context_id }}</p>
      <ul><li v-for="limitation in data.context.content.limitations" :key="limitation">{{ limitation }}</li></ul>
      <RawData title="完整单账号诊断上下文（PostgreSQL 原样存储）" :value="data.context.content" />
    </template>
  </template>
</template>
