<script setup lang="ts">
import { ref, watch } from 'vue'
import { get, query, useLoad } from '../api'
import type { Exclusion, Page, Proposal } from '../types'
import { label } from '../format'
import LoadState from './LoadState.vue'
import RawData from './RawData.vue'
const props = defineProps<{ runId: string; account: string; kind: 'candidates' | 'exclusions'; title: string }>()
const opened = ref(false), page = ref(1)
watch(() => [props.runId, props.account], () => { page.value = 1 })
const { data, loading, error, reload } = useLoad(() => [props.runId, props.account, opened.value, page.value], signal =>
  opened.value ? get<Page<Proposal | Exclusion>>(`/runs/${props.runId}/${props.kind}` + query({ account: props.account, limit: 50, offset: (page.value - 1) * 50 }), signal) : Promise.resolve(null))
function toggle(event: Event) { opened.value = (event.target as HTMLDetailsElement).open }
</script>
<template>
  <details class="archive-panel" @toggle="toggle"><summary>{{ title }}</summary>
    <template v-if="opened">
      <LoadState :loading="loading" :error="error" @retry="reload" />
      <template v-if="data">
        <p class="muted">{{ account ? `当前账号 ${account}` : '本批次全部账号' }} · 共 {{ data.total }} 条观察记录</p>
        <el-table :data="data.items" :max-height="480" border empty-text="没有符合条件的记录。">
          <el-table-column prop="account_id" label="账号" width="95" />
          <el-table-column prop="statistical_day" label="UTC 统计日" width="125" />
          <el-table-column label="事件" min-width="265"><template #default="{ row }"><code>{{ row.evidence?.event_name ?? row.event_name }}</code></template></el-table-column>
          <el-table-column prop="platform" label="平台" width="95" /><el-table-column prop="records" label="次数" width="80" />
          <el-table-column label="选样 / 排除原因" min-width="200"><template #default="{ row }">{{ label(row.selection?.reason ?? row.reason) }}</template></el-table-column>
          <el-table-column label="归档记录" min-width="130"><template #default="{ row }"><RawData title="完整记录" :value="row" /></template></el-table-column>
        </el-table>
        <el-pagination v-model:current-page="page" :page-size="50" :total="data.total" layout="prev, pager, next" :pager-count="5" />
      </template>
    </template>
  </details>
</template>
