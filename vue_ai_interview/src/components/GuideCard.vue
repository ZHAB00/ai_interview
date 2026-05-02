<script setup>
import { ref, onMounted } from 'vue'

const emit = defineEmits(['close'])
const visible = ref(false)

onMounted(() => {
  const shown = localStorage.getItem('guide_shown')
  if (!shown) {
    visible.value = true
  }
})

function handleClose() {
  visible.value = false
  localStorage.setItem('guide_shown', '1')
  emit('close')
}
</script>

<template>
  <el-dialog v-model="visible" title="欢迎使用 AI面试官" width="480px" :close-on-click-modal="false">
    <div class="guide-body">
      <div class="guide-step" v-for="(step, idx) in steps" :key="idx">
        <span class="step-num">{{ idx + 1 }}</span>
        <div class="step-content">
          <p class="step-title">{{ step.title }}</p>
          <p class="step-desc">{{ step.desc }}</p>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button type="primary" @click="handleClose">知道了</el-button>
    </template>
  </el-dialog>
</template>

<script>
export const steps = [
  { title: '上传简历', desc: '支持 PDF、Word、图片格式，系统自动解析简历信息' },
  { title: '配置面试', desc: '选择目标岗位、难度和面试模式，系统智能匹配合适的题目' },
  { title: '开始对话', desc: '与AI面试官进行实时语音对话，模拟真实面试场景' },
  { title: '查看报告', desc: '面试结束后获取能力画像、综合评语和错误解析报告' }
]
</script>

<style scoped>
.guide-body {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}
.guide-step {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}
.step-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}
</style>
