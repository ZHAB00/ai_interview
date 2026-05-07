<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps({
  totalSeconds: { type: Number, default: 2700 }, // 45 minutes
  initialRemaining: { type: Number, default: null } // override for resume
})

const emit = defineEmits(['expired', 'warning'])

const remaining = ref(props.initialRemaining ?? props.totalSeconds)
const isRunning = ref(true)
let timer = null

watch(() => props.initialRemaining, (val) => {
  if (val != null) {
    remaining.value = val
  }
})

const display = computed(() => {
  const m = Math.floor(remaining.value / 60)
  const s = remaining.value % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

const isWarning = computed(() => remaining.value <= 300) // last 5 min
const isCritical = computed(() => remaining.value <= 120) // last 2 min
const isBuffer = computed(() => remaining.value <= 0)

function start() {
  if (timer) return
  isRunning.value = true
  timer = setInterval(() => {
    if (remaining.value > 0) {
      remaining.value--
    } else {
      stop()
      emit('expired')
    }
  }, 1000)
}

function stop() {
  clearInterval(timer)
  timer = null
  isRunning.value = false
}

function pause() {
  clearInterval(timer)
  timer = null
  isRunning.value = false
}

function resume() {
  if (!isRunning.value) start()
}

watch(() => isCritical.value, (val) => {
  if (val) emit('warning')
})

onMounted(start)
onUnmounted(stop)

defineExpose({ remaining, pause, resume, stop, start })
</script>

<template>
  <div class="countdown" :class="{ warning: isWarning, critical: isCritical, buffer: isBuffer }">
    <el-icon :size="16"><Clock /></el-icon>
    <span class="countdown-display">{{ display }}</span>
  </div>
</template>

<style scoped>
.countdown {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}
.countdown-display {
  min-width: 50px;
}
.countdown.warning {
  color: var(--color-warning);
}
.countdown.critical {
  color: var(--color-error);
  animation: blink 1s ease-in-out infinite;
}
.countdown.buffer {
  color: var(--color-error);
  animation: blink 0.5s ease-in-out infinite;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
