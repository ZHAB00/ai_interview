<script setup>
import { computed } from 'vue'
import { AI_STATUS } from '../utils/constants.js'

const props = defineProps({
  status: { type: String, default: AI_STATUS.LISTENING }
})

const config = computed(() => {
  switch (props.status) {
    case AI_STATUS.LISTENING:
      return { icon: 'Microphone', color: '#4A7C59', text: '聆听中', pulse: true }
    case AI_STATUS.THINKING:
      return { icon: 'Loading', color: '#C27A3D', text: '思考中...', pulse: false }
    case AI_STATUS.SPEAKING:
      return { icon: 'ChatDotRound', color: '#2B3A67', text: '正在回复', pulse: false }
    case AI_STATUS.MUTED:
      return { icon: 'Mute', color: '#C27A3D', text: '已静音', pulse: false }
    default:
      return { icon: 'Microphone', color: '#4A7C59', text: '聆听中', pulse: true }
  }
})
</script>

<template>
  <span class="ai-status" :style="{ color: config.color }">
    <span class="status-icon" :class="{ pulse: config.pulse }">
      <el-icon v-if="config.icon === 'Microphone'"><Microphone /></el-icon>
      <el-icon v-else-if="config.icon === 'Loading'"><Loading /></el-icon>
      <el-icon v-else-if="config.icon === 'ChatDotRound'"><ChatDotRound /></el-icon>
      <el-icon v-else><Mute /></el-icon>
    </span>
    <span class="status-label">{{ config.text }}</span>
  </span>
</template>

<style scoped>
.ai-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.status-icon {
  display: flex;
  align-items: center;
}
.status-icon.pulse .el-icon {
  animation: pulse-glow 1.5s ease-in-out infinite;
}
.status-label {
  white-space: nowrap;
}
@keyframes pulse-glow {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
