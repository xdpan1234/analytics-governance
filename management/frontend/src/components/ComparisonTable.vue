<script setup lang="ts">
import { computed } from 'vue'
import type { Comparison } from '../types'
import { label, metric } from '../format'
import RawData from './RawData.vue'
const props = defineProps<{ comparison: Comparison }>()
const rows = computed(() => (['records', 'identified_accounts', 'result_rate'] as const).map(key => ({ key, ...props.comparison[key] })))
const names = { records: '记录数', identified_accounts: '去重账号', result_rate: '结果率' }
</script>
<template>
  <el-table :data="rows" border>
    <el-table-column label="指标" min-width="105"><template #default="{ row }">{{ names[row.key as keyof typeof names] }}</template></el-table-column>
    <el-table-column label="本期" min-width="100"><template #default="{ row }">{{ metric(row.current, row.key === 'result_rate') }}</template></el-table-column>
    <el-table-column label="参考" min-width="100"><template #default="{ row }">{{ metric(row.reference, row.key === 'result_rate') }}</template></el-table-column>
    <el-table-column label="差值" min-width="150"><template #default="{ row }">
      {{ row.key === 'result_rate' && row.delta_percentage_points != null ? `${row.delta_percentage_points > 0 ? '+' : ''}${row.delta_percentage_points.toFixed(2)} 个百分点` : metric(row.delta) }}
    </template></el-table-column>
    <el-table-column label="相对变化" min-width="110"><template #default="{ row }">{{ metric(row.relative_change, true) }}</template></el-table-column>
    <el-table-column label="参考天数 / 状态" min-width="165"><template #default="{ row }">{{ row.reference_days }}/{{ row.expected_reference_days }} · {{ label(row.status) }}</template></el-table-column>
  </el-table>
  <RawData title="比较状态及不可计算原因" :value="comparison" />
</template>
