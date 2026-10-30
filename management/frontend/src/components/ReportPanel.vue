<script setup lang="ts">
import { ref } from 'vue'
import type { EventMetric, ReportContent } from '../types'
import { label, metric } from '../format'
import RawData from './RawData.vue'
import ComparisonTable from './ComparisonTable.vue'
const props = defineProps<{ report: ReportContent }>()
const selected = ref<EventMetric | null>(null)
function selectEvent(name: string) { selected.value = props.report.top10.find(event => event.event_name === name) ?? null }
</script>
<template>
  <h2>日报 Top10</h2>
  <p class="muted">统计日 {{ report.statistical_day }} · UTC；结果率沿用原指标定义。环比与基线为全筛选人群，不能当成单用户基线。</p>
  <dl class="stats">
    <div><dt>基线方法</dt><dd>{{ label(report.baseline_summary.method) }}</dd></div>
    <div><dt>基线可用天数</dt><dd>{{ report.baseline_summary.available_days }}/{{ report.baseline_summary.expected_days }}</dd></div>
    <div><dt>数据质量</dt><dd>{{ label(report.quality.status) }}</dd></div>
  </dl>
  <el-table :data="report.top10" border empty-text="该统计日没有 Top10 记录。">
    <el-table-column type="index" label="排名" width="65" />
    <el-table-column label="事件 / 解释" min-width="285"><template #default="{ row }">
      <code>{{ row.event_name }}</code><el-button link type="primary" class="detail-link" @click="selectEvent(row.event_name)">查看原因、分母与比较口径</el-button>
    </template></el-table-column>
    <el-table-column prop="records" label="记录数" min-width="90" /><el-table-column prop="identified_accounts" label="去重账号" min-width="100" />
    <el-table-column label="结果率" min-width="165"><template #default="{ row }">{{ metric(row.result_rate, true) }}<small>{{ label(row.result_rate_status) }}</small></template></el-table-column>
    <el-table-column label="记录数环比" min-width="115"><template #default="{ row }">{{ metric(row.previous_day_comparison.records.relative_change, true) }}</template></el-table-column>
    <el-table-column label="基线记录数" min-width="115"><template #default="{ row }">{{ metric(row.baseline_comparison.records.reference) }}</template></el-table-column>
    <el-table-column label="较基线变化" min-width="115"><template #default="{ row }">{{ metric(row.baseline_comparison.records.relative_change, true) }}</template></el-table-column>
  </el-table>
  <RawData title="数据质量、窗口与表覆盖" :value="{ quality: report.quality, table_coverage: report.table_coverage, window: report.window, baseline_summary: report.baseline_summary }" />
  <RawData title="全部事件及比较指标（原样归档）" :value="report.events" />
  <el-drawer :model-value="selected !== null" :title="selected?.event_name ?? '指标详情'" size="min(960px, 100vw)" @close="selected = null">
    <template v-if="selected">
      <p>统计日 {{ report.statistical_day }} · 全筛选人群</p>
      <h3>较前一 UTC 日</h3><ComparisonTable :comparison="selected.previous_day_comparison" />
      <h3>前 7 日基线</h3><ComparisonTable :comparison="selected.baseline_comparison" />
      <RawData title="事件完整指标、原因、分母及平台版本分布" :value="selected" />
    </template>
  </el-drawer>
</template>
