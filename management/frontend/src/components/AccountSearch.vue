<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{ account: string }>()
const emit = defineEmits<{ search: [account: string] }>()
const input = ref(props.account)
watch(() => props.account, value => { input.value = value })
</script>
<template>
  <form class="search-form" @submit.prevent="emit('search', input.trim())">
    <label for="account-search">账号 ID（精确查询）</label>
    <div class="form-line">
      <el-input id="account-search" v-model="input" maxlength="64" inputmode="numeric" placeholder="输入业务账号 ID" clearable />
      <el-button type="primary" native-type="submit">查询</el-button>
    </div>
  </form>
</template>
