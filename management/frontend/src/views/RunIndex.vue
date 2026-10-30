<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { get, query, useLoad } from '../api'
import { label, utc } from '../format'
import type { Page, RunSummary } from '../types'
import AccountSearch from '../components/AccountSearch.vue'
import LoadState from '../components/LoadState.vue'

const route = useRoute(), router = useRouter()
const account = computed(() => String(route.query.account ?? ''))
const { data, loading, error, reload } = useLoad(() => route.path + JSON.stringify(route.query), signal =>
  get<Page<RunSummary>>('/runs' + query({ account: account.value }), signal))
function search(value: string) { router.push({ path: '/', query: value ? { account: value } : {} }) }
</script>
<template>
  <h1>分析批次</h1>
  <AccountSearch :account="account" @search="search" />
  <LoadState :loading="loading" :error="error" @retry="reload" />
  <template v-if="data">
    <p class="muted">最近 {{ data.limit }} 个批次；同一归档重复导入只保留一条批次。</p>
    <el-table :data="data.items" empty-text="没有符合条件的批次。" border>
      <el-table-column label="请求统计日 / 批次" min-width="205"><template #default="{ row }">
        <RouterLink :to="`/runs/${row.run_id}`">{{ row.target_day }}</RouterLink><small class="mono">{{ row.run_id.slice(0, 16) }}…</small>
      </template></el-table-column>
      <el-table-column label="数据状态" min-width="135"><template #default="{ row }"><el-tag type="warning">{{ label(row.data_status) }}</el-tag></template></el-table-column>
      <el-table-column label="计算状态" min-width="125"><template #default="{ row }"><el-tag>{{ label(row.process_status) }}</el-tag></template></el-table-column>
      <el-table-column prop="reports" label="日报" width="80" /><el-table-column prop="accounts" label="候选账号" width="100" />
      <el-table-column prop="findings" label="关联线索" width="100" />
      <el-table-column label="入库时间 UTC" min-width="225"><template #default="{ row }">{{ utc(row.created_at) }}</template></el-table-column>
    </el-table>
    <p v-if="account"><RouterLink :to="`/users/${account}`">查看该用户的归档批次</RouterLink></p>
  </template>
</template>
