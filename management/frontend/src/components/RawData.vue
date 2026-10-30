<script setup lang="ts">
import { ref } from 'vue'
defineProps<{ title: string; value: unknown }>()
const open = ref(false)
function toggle(event: Event) { open.value = (event.target as HTMLDetailsElement).open }
</script>

<template>
  <details class="raw-data" @toggle="toggle">
    <summary>{{ title }}</summary>
    <pre v-if="open">{{ JSON.stringify(value, null, 2) }}</pre>
  </details>
</template>
