<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { get, useLoad } from './api'
import type { Meta } from './types'
const { data, loading, error, reload } = useLoad(() => 'meta', signal => get<Meta>('/meta', signal))
</script>
<template>
  <el-config-provider :locale="zhCn">
  <a class="skip" href="#main">跳到内容</a>
  <header class="app-header"><nav aria-label="主导航">
    <RouterLink class="brand" to="/">埋点分析管理</RouterLink>
    <span class="header-note">冻结回放 · 本机只读</span>
    <RouterLink to="/">分析批次</RouterLink><RouterLink to="/users">按用户查询</RouterLink>
  </nav></header>
  <main id="main">
    <p v-if="data" class="scope">{{ data.scope }}</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button @click="reload">重新连接</el-button></el-alert>
    <el-skeleton v-else-if="loading" :rows="1" animated />
    <el-alert class="boundary" type="warning" :closable="false" show-icon
      title="当前为账号级候选预览，实例目标尚未解析；问题推断等待日志验证。采集任务 0 · 推送 0。" />
    <RouterView />
  </main>
  <footer>仅本机操作者访问指定 scope。统计日期与聚合窗口为 UTC；不构造逐事件时间线。</footer>
  </el-config-provider>
</template>
