<script setup>
import { computed } from 'vue'
import { useInterviewStore } from '../stores/interviewStore.js'

const interviewStore = useInterviewStore()

const statusConfig = computed(() => {
  switch (interviewStore.wsStatus) {
    case 'connected':
      return { color: '#4A7C59', text: '已连接' }
    case 'connecting':
    case 'reconnecting':
      return { color: '#C27A3D', text: '重连中...' }
    case 'disconnected':
    default:
      return { color: '#D14343', text: '已断开' }
  }
})
</script>

<template>
  <span class="network-status">
    <span class="status-dot" :style="{ background: statusConfig.color }"></span>
    <span class="status-text">{{ statusConfig.text }}</span>
  </span>
</template>

<style scoped>
.network-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
</style>
