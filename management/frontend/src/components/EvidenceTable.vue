<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { Observation } from '../types'
import { label, utc } from '../format'
import RawData from './RawData.vue'
const props = defineProps<{ observations: Observation[] }>()
const route = useRoute(), page = ref(1), focused = ref('')
const sorted = computed(() => [...props.observations].sort((a, b) =>
  b.statistical_day.localeCompare(a.statistical_day) || b.event_name.localeCompare(a.event_name)))
const rows = computed(() => sorted.value.slice((page.value - 1) * 25, page.value * 25))
watch(() => [route.hash, props.observations], async () => {
  if (!route.hash.startsWith('#fact-')) return
  const id = route.hash.slice(6), index = sorted.value.findIndex(fact => fact.fact_id === id)
  if (index < 0) return
  focused.value = id; page.value = Math.floor(index / 25) + 1
  await nextTick()
  const element = document.getElementById(`fact-${id}`)
  element?.scrollIntoView({ block: 'center' })
  element?.focus({ preventScroll: true })
}, { immediate: true, flush: 'post' })
function rowClass({ row }: { row: Observation }) { return row.fact_id === focused.value ? 'fact-selected' : '' }
</script>
<template>
  <el-table :data="rows" :row-class-name="rowClass" :max-height="640" border empty-text="该上下文没有埋点聚合记录。">
    <el-table-column label="事实 ID" min-width="170"><template #default="{ row }">
      <span :id="`fact-${row.fact_id}`" tabindex="-1" class="fact-anchor"><code>{{ row.fact_id.slice(0, 12) }}</code></span>
      <RawData title="事实摘要" :value="row" />
    </template></el-table-column>
    <el-table-column prop="statistical_day" label="UTC 日" width="125" />
    <el-table-column label="事件" min-width="285"><template #default="{ row }"><code>{{ row.event_name }}</code></template></el-table-column>
    <el-table-column label="平台 / 版本" min-width="120"><template #default="{ row }">{{ row.platform }}<small>{{ row.app_version ?? '未提供' }}</small></template></el-table-column>
    <el-table-column prop="records" label="次数" width="80" />
    <el-table-column label="原因" min-width="170"><template #default="{ row }">{{ row.reason ?? '未提供 / 不适用' }}</template></el-table-column>
    <el-table-column label="首末时间 UTC" min-width="285"><template #default="{ row }">{{ utc(row.first_event_at) }}<small>{{ utc(row.last_event_at) }}</small></template></el-table-column>
    <el-table-column label="质量" min-width="180"><template #default="{ row }">{{ label(row.parameter_status) }}<small>{{ row.reason_status ? label(row.reason_status) : '未标记原因问题' }}</small></template></el-table-column>
  </el-table>
  <el-pagination v-model:current-page="page" :page-size="25" :total="observations.length" layout="total, prev, pager, next" :pager-count="5" />
</template>
