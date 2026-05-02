<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  from: { type: String, default: '' },
  to: { type: String, default: '' },
  message: { type: String, default: '' },
  autoClose: { type: Number, default: 1500 }
})

const emit = defineEmits(['close'])
const visible = ref(false)

watch(() => props.to, (newVal) => {
  if (newVal) {
    visible.value = true
    if (props.autoClose > 0) {
      setTimeout(() => {
        visible.value = false
        emit('close')
      }, props.autoClose)
    }
  }
})

function handleContinue() {
  visible.value = false
  emit('close')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="stage-fade">
      <div v-if="visible" class="stage-overlay" @click="handleContinue">
        <div class="stage-card">
          <p v-if="from" class="stage-from">{{ from }} 阶段已完成</p>
          <p class="stage-arrow">{{ from ? '即将进入' : '面试开始' }}</p>
          <p class="stage-to">{{ to }}</p>
          <p v-if="message" class="stage-message">{{ message }}</p>
          <el-button text size="small" @click="handleContinue" style="margin-top: 16px">继续</el-button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.stage-overlay {
  position: fixed;
  inset: 0;
  background: rgba(247, 248, 250, 0.94);
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stage-card {
  text-align: center;
  padding: 48px 60px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  animation: stage-in 150ms ease-out;
}
.stage-from {
  font-size: 15px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.stage-arrow {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.stage-to {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-accent);
}
.stage-message {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 8px;
}
@keyframes stage-in {
  from { transform: scale(0.96); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
.stage-fade-enter-active { transition: opacity 150ms ease-out; }
.stage-fade-leave-active { transition: opacity 120ms ease-in; }
.stage-fade-enter-from,
.stage-fade-leave-to { opacity: 0; }
</style>
