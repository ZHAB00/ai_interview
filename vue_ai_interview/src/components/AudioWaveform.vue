<script setup>
import { computed } from 'vue'

const props = defineProps({
  active: { type: Boolean, default: false },
  bars: { type: Number, default: 5 }
})

// Generate random-looking but stable heights for each bar
const barCount = computed(() => props.active ? props.bars : 0)
</script>

<template>
  <div class="waveform" :class="{ active }">
    <span
      v-for="i in barCount"
      :key="i"
      class="wave-bar"
      :style="{ animationDelay: `${(i - 1) * 0.12}s` }"
    ></span>
  </div>
</template>

<style scoped>
.waveform {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 24px;
}
.wave-bar {
  width: 3px;
  height: 6px;
  background: var(--color-accent);
  border-radius: 1px;
}
.waveform.active .wave-bar {
  animation: wave 0.6s ease-in-out infinite alternate;
}
@keyframes wave {
  0% { height: 4px; }
  100% { height: 22px; }
}
</style>
