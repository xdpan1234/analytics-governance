<script setup lang="ts">
defineProps<{ loading: boolean; error: string }>()
defineEmits<{ retry: [] }>()
</script>
<template>
  <div v-if="loading" role="status" aria-label="正在查询" class="loading"><el-skeleton :rows="4" animated /></div>
  <el-alert v-else-if="error" :title="error" type="error" show-icon :closable="false" role="alert">
    <el-button @click="$emit('retry')">重试</el-button>
  </el-alert>
</template>
