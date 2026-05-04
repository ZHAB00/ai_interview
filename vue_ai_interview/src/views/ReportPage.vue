<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useReport } from '../composables/useReport.js'
import { DIMENSIONS, PASS_THRESHOLD } from '../utils/constants.js'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'

const route = useRoute()
const interviewId = route.params.interviewId
const { loading, report, error, startPolling, submitFeedback } = useReport(interviewId)

// --- Radar Chart ---
const chartRef = ref(null)
let chartInstance = null

function renderRadar() {
  if (!chartRef.value || !report.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }

  const dims = DIMENSIONS
  const userScores = dims.map(d => report.value.dimensions[d] || 0)
  const thresholdScores = dims.map(() => PASS_THRESHOLD)

  const option = {
    radar: {
      center: ['50%', '52%'],
      radius: '65%',
      indicator: dims.map(d => ({ name: d, max: 100 })),
      axisName: { fontSize: 12, color: '#6B7280' },
      shape: 'circle',
      splitArea: {
        areaStyle: { color: ['#F7F8FA', '#FFFFFF'] }
      },
      splitLine: { lineStyle: { color: '#E5E7EB' } }
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: userScores,
            name: '你的得分',
            areaStyle: { color: 'rgba(43, 58, 103, 0.12)' },
            lineStyle: { color: '#2B3A67', width: 2 },
            itemStyle: { color: '#2B3A67' },
            symbol: 'circle',
            symbolSize: 5
          },
          {
            value: thresholdScores,
            name: `及格线 (${PASS_THRESHOLD}分)`,
            areaStyle: { color: 'transparent' },
            lineStyle: { color: '#D0D5DD', width: 1.5, type: 'dashed' },
            itemStyle: { color: '#D0D5DD' },
            symbol: 'none'
          }
        ]
      }
    ],
    tooltip: {
      trigger: 'item'
    },
    legend: {
      bottom: 8,
      data: ['你的得分', `及格线 (${PASS_THRESHOLD}分)`],
      textStyle: { fontSize: 12, color: '#6B7280' }
    }
  }

  chartInstance.setOption(option, true)
}

watch(report, (val) => {
  if (val) nextTick(renderRadar)
})

onUnmounted(() => {
  chartInstance?.dispose()
})

// --- Replay ---
const audioRef = ref(null)
const transcriptContainer = ref(null)
const currentTranscriptIndex = ref(-1)
const isPlaying = ref(false)

function handleAudioTimeUpdate() {
  // Simplified — in production would sync with timestamps
  if (!audioRef.value) return
  const progress = audioRef.value.currentTime / (audioRef.value.duration || 1)
  currentTranscriptIndex.value = Math.floor(progress * (allTranscripts.value.length - 1))
  // Auto-scroll
  const el = document.querySelector(`.transcript-row.active`)
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

function jumpToTime(index) {
  if (!audioRef.value) return
  const ratio = allTranscripts.value.length > 1
    ? index / (allTranscripts.value.length - 1)
    : 0
  audioRef.value.currentTime = ratio * (audioRef.value.duration || 0)
}

// Collect all question-answer pairs as transcript
const allTranscripts = computed(() => {
  const items = []
  if (!report.value?.stage_breakdown) return items
  for (const stage of report.value.stage_breakdown) {
    for (const q of (stage.questions || [])) {
      items.push({
        stage: stage.stage,
        question: q.question_text,
        answer: q.user_answer_summary,
        score: q.score,
        audioUrl: q.user_audio_url
      })
    }
  }
  return items
})

// --- Feedback Dialog ---
const feedbackDialog = ref(false)
const feedbackTarget = ref(null)
const feedbackForm = ref({
  type: '具体错误',
  reason: ''
})
const feedbackSubmitting = ref(false)
const feedbackTypes = ['事实错误', '评分不公', '其他']

function openFeedback(errorItem) {
  feedbackTarget.value = errorItem
  feedbackForm.value = { type: '事实错误', reason: '' }
  feedbackDialog.value = true
}

async function handleFeedbackSubmit() {
  feedbackSubmitting.value = true
  try {
    const ok = await submitFeedback({
      type: feedbackForm.value.type,
      reason: feedbackForm.value.reason,
      snippet: feedbackTarget.value?.snippet || ''
    })
    if (ok) {
      ElMessage.success('感谢反馈，我们会尽快核实')
      feedbackDialog.value = false
    }
  } catch {
    ElMessage.error('提交失败，请稍后重试')
  } finally {
    feedbackSubmitting.value = false
  }
}

// --- Lifecycle ---
onMounted(() => {
  startPolling()
})

// --- Computed ---
const errorItems = computed(() => {
  const items = []
  if (!report.value?.stage_breakdown) return items
  for (const stage of report.value.stage_breakdown) {
    for (const q of (stage.questions || [])) {
      for (const e of (q.errors || [])) {
        items.push({ ...e, stage: stage.stage, question: q.question_text })
      }
    }
  }
  return items
})

const errorTypeConfig = (type) => {
  if (type === 'fact_error') return { text: '事实错误', class: 'error-fact' }
  if (type === 'depth_error') return { text: '深度不足', class: 'error-depth' }
  return { text: type, class: '' }
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="report-page">
    <!-- Loading -->
    <div v-if="loading" class="report-loading">
      <el-icon :size="36" class="spin"><Loading /></el-icon>
      <p>报告生成中，请稍候...</p>
      <p class="hint">面试结束，AI正在分析您的表现并生成报告</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="report-error">
      <el-empty :description="error">
        <el-button @click="startPolling">重新获取</el-button>
      </el-empty>
    </div>

    <!-- Report Content -->
    <template v-else-if="report">
      <div class="report-container">
        <!-- Top Overview -->
        <section class="card overview-card">
          <div class="overview-main">
            <div class="score-section">
              <span class="score-number">{{ report.overall_score }}</span>
              <span class="score-label">总分</span>
            </div>
            <div class="verdict-section">
              <el-tag
                :type="report.passed ? 'success' : 'danger'"
                size="large"
                class="verdict-tag"
              >
                {{ report.passed ? '通过' : '不通过' }}
              </el-tag>
              <p class="verdict-threshold">及格线：{{ report.threshold }} 分</p>
            </div>
            <div class="dim-summary">
              <div v-for="dim in DIMENSIONS" :key="dim" class="dim-item">
                <span class="dim-name">{{ dim }}</span>
                <span class="dim-score" :class="{ below: (report.dimensions[dim] || 0) < PASS_THRESHOLD }">
                  {{ report.dimensions[dim] || 0 }}
                </span>
              </div>
            </div>
          </div>
          <!-- Resume deduction -->
          <div v-if="report.resume_deduction" class="deduction-row">
            <el-alert
              :title="`简历扣分：${report.resume_deduction} 分 — ${report.deduction_reason || ''}`"
              type="warning"
              :closable="false"
            />
          </div>
        </section>

        <!-- Radar Chart -->
        <section class="card radar-card">
          <h3 class="section-title">能力画像</h3>
          <div ref="chartRef" class="chart-container"></div>
        </section>

        <!-- Overall Comment -->
        <section v-if="report.overall_comment" class="card comment-card">
          <h3 class="section-title">综合评语</h3>
          <p class="comment-text">{{ report.overall_comment }}</p>
        </section>

        <!-- Error Analysis -->
        <section v-if="errorItems.length" class="card error-card">
          <h3 class="section-title">错误解析</h3>
          <div class="error-list">
            <div
              v-for="(item, idx) in errorItems"
              :key="idx"
              class="error-row"
              :class="errorTypeConfig(item.type).class"
            >
              <div class="error-header">
                <span class="error-type-tag" :class="errorTypeConfig(item.type).class">
                  {{ errorTypeConfig(item.type).text }}
                </span>
                <span class="error-stage">{{ item.stage }}</span>
                <span class="error-question">{{ item.question }}</span>
                <el-button text size="small" type="warning" class="error-report-btn" @click="openFeedback(item)">
                  反馈纠正
                </el-button>
              </div>
              <div class="error-body">
                <div class="error-block">
                  <span class="error-label">错误片段</span>
                  <p class="error-value snippet">"{{ item.snippet }}"</p>
                </div>
                <div class="error-block">
                  <span class="error-label">纠正</span>
                  <p class="error-value">{{ item.correction }}</p>
                </div>
                <el-collapse class="suggestion-fold">
                  <el-collapse-item title="查看优化建议">
                    <p>{{ item.suggestion }}</p>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </div>
        </section>

        <!-- Stage Breakdown -->
        <section v-if="report.stage_breakdown?.length" class="card stage-card">
          <h3 class="section-title">分阶段点评</h3>
          <div v-for="(stage, idx) in report.stage_breakdown" :key="idx" class="stage-block">
            <h4 class="stage-name">{{ stage.stage }}</h4>
            <div v-for="(q, qi) in (stage.questions || [])" :key="qi" class="stage-q-item">
              <p class="sq-question">Q: {{ q.question_text }}</p>
              <p class="sq-answer">A: {{ q.user_answer_summary }}</p>
              <div class="sq-meta">
                <span>得分：<strong>{{ q.score }}</strong></span>
                <span v-if="q.strengths" class="strength">优势：{{ q.strengths }}</span>
                <span v-if="q.weaknesses" class="weakness">不足：{{ q.weaknesses }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Interview Replay -->
        <section v-if="allTranscripts.length" class="card replay-card">
          <h3 class="section-title">面试回放</h3>
          <div class="replay-layout">
            <div class="replay-audio">
              <audio
                ref="audioRef"
                controls
                @timeupdate="handleAudioTimeUpdate"
                @play="isPlaying = true"
                @pause="isPlaying = false"
                style="width: 100%"
              >
                <source :src="allTranscripts[0]?.audioUrl" type="audio/wav">
              </audio>
              <p class="audio-hint" v-if="!allTranscripts[0]?.audioUrl">完整录音可在后端就绪后播放</p>
            </div>
            <div class="replay-transcript" ref="transcriptContainer">
              <div
                v-for="(item, idx) in allTranscripts"
                :key="idx"
                class="transcript-row"
                :class="{ active: idx === currentTranscriptIndex }"
                @click="jumpToTime(idx)"
              >
                <span class="tr-index">#{{ idx + 1 }}</span>
                <div class="tr-content">
                  <p class="tr-question">{{ item.question }}</p>
                  <p class="tr-answer">{{ item.answer }}</p>
                </div>
                <span class="tr-score">{{ item.score }}分</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Meta -->
        <p class="report-meta">
          报告生成时间：{{ formatTime(report.generated_at) }}
        </p>
      </div>
    </template>

    <!-- Feedback Dialog -->
    <el-dialog v-model="feedbackDialog" title="举报/纠正" width="420px">
      <el-form :model="feedbackForm" label-position="top">
        <el-form-item label="举报类型">
          <el-select v-model="feedbackForm.type" style="width: 100%">
            <el-option v-for="t in feedbackTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="详细说明">
          <el-input v-model="feedbackForm.reason" type="textarea" :rows="3" placeholder="请描述您认为不正确的地方..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackDialog = false">取消</el-button>
        <el-button type="primary" :loading="feedbackSubmitting" @click="handleFeedbackSubmit">
          提交反馈
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.report-page {
  min-height: calc(100vh - 48px - 38px);
  background: var(--color-bg);
  padding-bottom: 48px;
}

/* Loading */
.report-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  color: var(--color-text-secondary);
}
.report-loading p { margin-top: 16px; font-size: 15px; }
.report-loading .hint { font-size: 13px; color: var(--color-text-secondary); margin-top: 6px; }
.spin { animation: spin 1s linear infinite; color: var(--color-accent); }
@keyframes spin { to { transform: rotate(360deg); } }

.report-error {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
}

/* Container */
.report-container {
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px;
}

/* Cards */
.card {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 24px;
  margin-bottom: 16px;
}
.section-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 16px;
}

/* Overview */
.overview-main {
  display: flex;
  align-items: center;
  gap: 32px;
}
.score-section {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.score-number {
  font-size: 48px;
  font-weight: 700;
  color: var(--color-text);
  line-height: 1;
}
.score-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}
.verdict-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.verdict-tag { font-size: 16px !important; padding: 6px 24px !important; }
.verdict-threshold {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.dim-summary {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 20px;
  flex: 1;
}
.dim-item {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}
.dim-name { color: var(--color-text-secondary); }
.dim-score { font-weight: 500; color: var(--color-success); }
.dim-score.below { color: var(--color-warning); }

.deduction-row {
  margin-top: 16px;
}

/* Radar */
.chart-container {
  width: 100%;
  height: 380px;
}

/* Comment */
.comment-text {
  font-size: 14px;
  color: var(--color-text);
  line-height: 1.8;
}

/* Error List */
.error-row {
  padding: 16px 0;
  border-bottom: 1px solid var(--color-border-light);
  border-left: 3px solid transparent;
  padding-left: 12px;
}
.error-row:last-child { border-bottom: none; }
.error-row.error-fact { border-left-color: #C27A3D; }
.error-row.error-depth { border-left-color: #D9A34A; }

.error-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.error-type-tag {
  display: inline-block;
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 2px;
  font-weight: 500;
}
.error-type-tag.error-fact { background: rgba(194, 122, 61, 0.1); color: #C27A3D; }
.error-type-tag.error-depth { background: rgba(217, 163, 74, 0.1); color: #D9A34A; }
.error-stage {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.error-question {
  font-size: 12px;
  color: var(--color-text);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.error-report-btn {
  flex-shrink: 0;
}

.error-body { }
.error-block {
  margin-bottom: 10px;
}
.error-label {
  display: block;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
.error-value {
  font-size: 13px;
  color: var(--color-text);
  line-height: 1.7;
  margin: 0;
}
.error-value.snippet {
  color: #C27A3D;
  font-style: italic;
  background: rgba(194, 122, 61, 0.04);
  padding: 6px 10px;
  border-radius: 2px;
}
.suggestion-fold {
  margin-top: 4px;
}
.suggestion-fold {
  margin-top: 4px;
}
.error-action {
  display: flex;
  align-items: flex-start;
}

/* Stage Breakdown */
.stage-block {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--color-border-light);
}
.stage-block:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
.stage-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-accent);
  margin-bottom: 12px;
}
.stage-q-item {
  padding: 10px 14px;
  background: var(--color-border-light);
  border-radius: 2px;
  margin-bottom: 8px;
}
.sq-question { font-size: 13px; color: var(--color-text); font-weight: 500; }
.sq-answer { font-size: 13px; color: var(--color-text-secondary); margin-top: 4px; }
.sq-meta {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.sq-meta .strength { color: var(--color-success); }
.sq-meta .weakness { color: var(--color-warning); }

/* Replay */
.replay-layout {
  display: flex;
  gap: 20px;
}
.replay-audio {
  width: 320px;
  flex-shrink: 0;
}
.audio-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 8px;
}
.replay-transcript {
  flex: 1;
  max-height: 360px;
  overflow-y: auto;
  border: 1px solid var(--color-border-light);
  border-radius: 2px;
}
.transcript-row {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid var(--color-border-light);
  transition: background 0.15s;
}
.transcript-row:hover { background: rgba(43, 58, 103, 0.03); }
.transcript-row.active { background: rgba(43, 58, 103, 0.06); }
.tr-index {
  font-size: 11px;
  color: var(--color-text-secondary);
  flex-shrink: 0;
  padding-top: 2px;
}
.tr-content { flex: 1; min-width: 0; }
.tr-question { font-size: 13px; color: var(--color-text); font-weight: 500; }
.tr-answer { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tr-score {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-accent);
  flex-shrink: 0;
}

.report-meta {
  text-align: center;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 8px;
}
/* ── Mobile (≤768px) ── */
@media (max-width: 768px) {
  .report-container {
    padding: 16px 12px;
  }

  .overview-main {
    flex-direction: column;
    gap: 16px;
  }

  .score-number {
    font-size: 36px;
  }

  .chart-container {
    height: 260px;
  }

  .replay-layout {
    flex-direction: column;
    gap: 12px;
  }

  .replay-audio {
    width: 100%;
  }

  .error-header {
    flex-wrap: wrap;
    gap: 4px;
  }

  .report-meta {
    font-size: 12px;
  }
}
</style>
