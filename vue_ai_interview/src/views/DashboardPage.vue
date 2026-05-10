<script setup>
import { reactive, ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { uploadResume } from '../services/resumeService.js'
import { createInterview, getInterviewHistory, getActiveInterview, toggleFavorite, deleteInterview as delIv } from '../services/interviewService.js'
import * as interviewService from '../services/interviewService.js'
import { ElMessageBox } from 'element-plus'
import { STAGES, INTERVIEW_MODE } from '../utils/constants.js'
import GuideCard from '../components/GuideCard.vue'
import { steps } from '../components/GuideCard.vue'

const router = useRouter()
const route = useRoute()
const viewMode = computed(() => route.query.view || 'default')
// Desktop: always show everything. Mobile: toggle based on viewMode.
const isHistoryView = computed(() => viewMode.value === 'history')

// --- Resume Upload State ---
const uploadState = ref('idle') // idle | uploading | parsing | done | error
const uploadProgress = ref(0)
const resumeData = ref(null)
const resumeId = ref('')
const isQuickStart = ref(false)
const uploadError = ref('')
const uploadFileList = ref([])
const uploadRef = ref(null)

// --- Interview Config State ---
const config = reactive({
  position: '',
  difficulty: '中级',
  mode: INTERVIEW_MODE.FULL,
  selectedStages: []
})

const startLoading = ref(false)
const newSkill = ref('')        // input for adding a custom skill
const skillEdited = ref(false)  // user has manually edited skills

// --- History ---
const history = ref([])
const historyLoading = ref(false)

// Computed
const showConfig = computed(() => uploadState.value === 'done')
const isStageMode = computed(() => config.mode === INTERVIEW_MODE.STAGE)

const positionOptions = [
  'AI Agent开发工程师',
  '后端开发工程师',
  '前端开发工程师',
  '全栈开发工程师',
  '数据分析师',
  '产品经理'
]

const difficultyOptions = ['初级', '中级', '高级']

// --- Position → Skills Mapping ---
const POSITION_SKILL_MAP = {
  'AI Agent开发工程师': ['Python', 'LangChain', 'LLM', 'RAG', 'Prompt Engineering', 'FastAPI', 'Docker'],
  '后端开发工程师':     ['Python', 'Java', 'Go', 'MySQL', 'Redis', 'Docker', 'Kubernetes', '微服务'],
  '前端开发工程师':     ['Vue.js', 'React', 'TypeScript', 'JavaScript', 'CSS', 'Node.js', 'Webpack'],
  '全栈开发工程师':     ['Python', 'Vue.js', 'React', 'TypeScript', 'MySQL', 'Docker', 'CI/CD'],
  '数据分析师':         ['Python', 'SQL', 'Pandas', 'NumPy', 'Tableau', '机器学习', '数据可视化'],
  '产品经理':           ['需求分析', '产品设计', '数据分析', '用户研究', '项目管理', 'Axure', 'Figma'],
}

// Watch position change → auto-update skills (unless user manually edited)
watch(() => config.position, (newPos) => {
  if (!newPos) return
  const mappedSkills = POSITION_SKILL_MAP[newPos]
  if (mappedSkills && !skillEdited.value) {
    if (resumeData.value) {
      resumeData.value.skills = [...mappedSkills]
    }
  }
  // Reset edit flag on position switch — user needs to confirm edits for new position
  skillEdited.value = false
})

function addSkill() {
  const skill = newSkill.value.trim()
  if (!skill) return
  if (!resumeData.value) return
  if (!resumeData.value.skills) resumeData.value.skills = []
  if (resumeData.value.skills.includes(skill)) {
    ElMessage.warning('技能已存在')
    return
  }
  resumeData.value.skills.push(skill)
  newSkill.value = ''
  skillEdited.value = true
}

function removeSkill(index) {
  if (!resumeData.value) return
  resumeData.value.skills.splice(index, 1)
  skillEdited.value = true
}

// --- Resume Upload ---
function handleFileChange(file) {
  uploadFileList.value = [file]
  handleUpload()
}

async function handleUpload() {
  if (!uploadFileList.value.length) return

  const file = uploadFileList.value[0].raw
  const formData = new FormData()
  formData.append('file', file)
  formData.append('position', config.position || 'AI Agent开发工程师')
  formData.append('difficulty', config.difficulty)

  uploadState.value = 'uploading'
  uploadProgress.value = 0
  uploadError.value = ''

  try {
    const { data } = await uploadResume(formData, (pct) => {
      uploadProgress.value = pct
    })

    uploadState.value = 'parsing'

    // Resume data is returned directly — simulate parsing delay for UX
    await new Promise(resolve => setTimeout(resolve, 1200))

    resumeData.value = data.parsed_data
    resumeId.value = data.resume_id
    config.position = data.parsed_data.position || config.position
    uploadState.value = 'done'
    ElMessage.success('简历解析完成')
  } catch (err) {
    uploadState.value = 'error'
    uploadError.value = err.response?.data?.error?.message || '简历上传或解析失败，请重试'
  }
}

function handleRetry() {
  uploadState.value = 'idle'
  uploadFileList.value = []
  uploadError.value = ''
  isQuickStart.value = false
}

function handleBackToUpload() {
  uploadState.value = 'idle'
  uploadFileList.value = []
  isQuickStart.value = false
}

// --- Interview Start ---
async function handleStartInterview() {
  // Pre-submit validation
  if (!config.position || !config.position.trim()) {
    ElMessage.warning('请选择目标岗位')
    return
  }
  if (!isQuickStart.value && !resumeId.value) {
    ElMessage.warning('请先上传简历或使用快速体验')
    return
  }

  startLoading.value = true
  try {
    const params = {
      position: config.position,
      difficulty: config.difficulty,
      mode: config.mode
    }
    // Only include resume_id for real uploaded resumes, not quick start
    if (resumeId.value && resumeId.value !== 'demo_resume') {
      params.resume_id = parseInt(resumeId.value, 10)
    }
    if (config.mode === INTERVIEW_MODE.STAGE) {
      params.selected_stages = config.selectedStages
    }

    const { data } = await createInterview(params)
    // Store ws_token for the interview room to use
    sessionStorage.setItem('ws_token', data.ws_token)
    sessionStorage.setItem('ws_url', data.ws_url)
    sessionStorage.setItem('interview_id', data.interview_id)
    router.push(`/interview/${data.interview_id}`)
  } catch (err) {
    const msg =
      err.response?.data?.error?.message ||
      (err.response?.data?.detail && (Array.isArray(err.response.data.detail)
        ? err.response.data.detail.map(d => d.msg).join('; ')
        : err.response.data.detail)) ||
      '创建面试失败，请检查网络连接或后端服务是否启动'
    ElMessage.error(msg)
  } finally {
    startLoading.value = false
  }
}

// --- Quick Start ---
function handleQuickStart() {
  const defaultPosition = 'AI Agent开发工程师'
  const defaultSkills = POSITION_SKILL_MAP[defaultPosition] || ['Python', 'FastAPI', 'Vue.js']

  resumeData.value = {
    name: '示例用户',
    phone: '13800000000',
    email: 'demo@example.com',
    education: [{ school: '示例大学', degree: '本科', major: '计算机科学', year: '2024' }],
    skills: [...defaultSkills],
    work_experience: [{ company: 'XX科技', position: '后端开发', duration: '2024-至今' }],
    project_experience: [{ name: 'AI面试系统', role: '核心开发', description: '基于大模型的模拟面试平台' }]
  }
  resumeId.value = '' // Quick start — no real resume, backend creates placeholder
  isQuickStart.value = true
  skillEdited.value = false
  config.position = defaultPosition
  config.difficulty = '中级'
  config.mode = INTERVIEW_MODE.FULL
  config.selectedStages = []
  uploadState.value = 'done'
  ElMessage.success('已加载示例简历，可直接开始面试体验')
}

// --- Load History ---
const historyPage = ref(1)
const historyTotal = ref(0)
const pageSize = 8

async function loadHistory(page = 1) {
  historyLoading.value = true
  historyPage.value = page
  try {
    const { data } = await getInterviewHistory(page, pageSize)
    history.value = data.items || []
    historyTotal.value = data.total
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
  }
}

async function toggleFav(iv) {
  try {
    const { data } = await interviewService.toggleFavorite(iv.interview_id)
    iv.is_favorited = data.favorited
    ElMessage.success(data.message)
    loadHistory(historyPage.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '操作失败')
  }
}

async function deleteInterviewItem(iv) {
  try {
    await ElMessageBox.confirm('确定删除这条面试记录？报告和录音也将永久删除。', '警告', { type: 'warning', confirmButtonText: '删除' })
    await interviewService.deleteInterview(iv.interview_id)
    ElMessage.success('已删除')
    loadHistory(historyPage.value)
  } catch { /* cancelled */ }
}

async function continueInterview() {
  try {
    const { data } = await getActiveInterview()
    if (data.active) {
      router.push(`/interview/${data.interview_id}`)
    } else {
      ElMessage.info('暂无进行中的面试')
    }
  } catch {
    ElMessage.error('获取面试状态失败')
  }
}

function viewReport(interviewId) {
  router.push(`/report/${interviewId}`)
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
}

const statusConfig = (status) => {
  const map = {
    created: { text: '待开始', type: 'info' },
    in_progress: { text: '进行中', type: 'warning' },
    completed: { text: '已完成', type: 'success' },
    abandoned: { text: '已放弃', type: 'info' }
  }
  return map[status] || map.created
}

const activeInterviewId = ref(null)
const activeRemaining = ref(0)
let activeTimer = null

function formatRemaining(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}分${s.toString().padStart(2, '0')}秒`
}

async function checkActiveInterview() {
  try {
    const { data } = await getActiveInterview()
    if (data.active) {
      activeInterviewId.value = data.interview_id
      activeRemaining.value = data.remaining_seconds || 0
      clearInterval(activeTimer)
      activeTimer = setInterval(() => {
        if (activeRemaining.value > 0) {
          activeRemaining.value--
        } else {
          activeInterviewId.value = null
          clearInterval(activeTimer)
        }
      }, 1000)
    }
  } catch { /* ignore */ }
}

onMounted(() => {
  checkActiveInterview()
  loadHistory()
})

onUnmounted(() => {
  clearInterval(activeTimer)
})

// Expose steps for GuideCard template
const guideSteps = steps
</script>

<template>
  <div class="dashboard-page" :class="{ 'view-history': isHistoryView }">
    <div class="page-container">
      <h1 class="page-title title-default">面试控制台</h1>
      <p class="page-desc title-default">上传简历，配置面试参数，开始您的模拟面试练习</p>
      <h1 class="page-title title-history">面试记录</h1>
      <section class="card upload-section" v-if="uploadState !== 'done'">
        <div class="section-header">
          <h3>第一步：上传简历</h3>
          <span class="section-hint">支持 PDF、Word 格式，最大 10MB</span>
        </div>

        <el-upload
          ref="uploadRef"
          class="upload-area"
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :accept="'.pdf,.docx'"
          :show-file-list="false"
          :disabled="uploadState === 'uploading' || uploadState === 'parsing'"
        >
          <el-icon class="upload-icon" :size="40"><UploadFilled /></el-icon>
          <div class="upload-text">
            <p>拖拽文件到此处，或 <em>点击上传</em></p>
            <p class="upload-formats">PDF / DOCX</p>
          </div>
        </el-upload>

        <!-- Upload Progress -->
        <div v-if="uploadState === 'uploading'" class="progress-bar">
          <el-progress :percentage="uploadProgress" :stroke-width="6" />
          <p class="progress-text">上传中 {{ uploadProgress }}%</p>
        </div>

        <!-- Error State -->
        <div v-if="uploadState === 'error'" class="upload-error">
          <el-alert :title="uploadError" type="error" show-icon />
          <el-button type="primary" @click="handleRetry" style="margin-top: 12px">重新上传</el-button>
        </div>

        <!-- Quick Start -->
        <div class="quick-start-hint">
          <span class="divider-text">或</span>
          <el-button text type="primary" @click="handleQuickStart">
            使用示例简历快速体验
          </el-button>
        </div>
      </section>

      <!-- Resume Parse Result + Config -->
      <template v-if="showConfig">
        <section class="card resume-summary">
          <div class="section-header">
            <h3>简历解析结果</h3>
            <div class="header-actions">
              <el-tag v-if="isQuickStart" size="small" type="info">快速体验</el-tag>
              <el-tag v-else size="small" type="success">解析完成</el-tag>
              <el-button text type="primary" size="small" @click="handleBackToUpload" style="margin-left: 8px">返回上传</el-button>
            </div>
          </div>
          <div class="summary-grid">
            <div class="summary-item">
              <span class="label">姓名</span>
              <span class="value">{{ resumeData?.name || '-' }}</span>
            </div>
            <div class="summary-item">
              <span class="label">学历</span>
              <span class="value">{{ resumeData?.education?.[0]?.school || '-' }} / {{ resumeData?.education?.[0]?.degree || '-' }}</span>
            </div>
            <div class="summary-item">
              <span class="label">联系方式</span>
              <span class="value">{{ resumeData?.phone || '-' }} / {{ resumeData?.email || '-' }}</span>
            </div>
            <div class="summary-item skills">
              <span class="label">技能</span>
              <span class="value">
                <el-tag
                  v-for="(skill, idx) in (resumeData?.skills || [])"
                  :key="skill"
                  size="small"
                  type="info"
                  closable
                  @close="removeSkill(idx)"
                >
                  {{ skill }}
                </el-tag>
                <el-input
                  v-if="resumeData"
                  v-model="newSkill"
                  size="small"
                  placeholder="添加技能"
                  style="width: 100px; margin-left: 4px;"
                  @keyup.enter="addSkill"
                />
                <el-button
                  v-if="resumeData"
                  size="small"
                  icon="Plus"
                  circle
                  style="margin-left: 4px;"
                  @click="addSkill"
                />
              </span>
            </div>
          </div>
        </section>

        <section class="card config-section">
          <div class="section-header">
            <h3>第二步：配置面试</h3>
          </div>

          <el-form :model="config" label-position="top">
            <el-form-item label="目标岗位">
              <el-select
                v-model="config.position"
                placeholder="请选择或搜索岗位"
                filterable
                style="width: 100%"
              >
                <el-option
                  v-for="pos in positionOptions"
                  :key="pos"
                  :label="pos"
                  :value="pos"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="难度选择">
              <el-radio-group v-model="config.difficulty">
                <el-radio-button
                  v-for="d in difficultyOptions"
                  :key="d"
                  :value="d"
                >
                  {{ d }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="面试模式">
              <el-radio-group v-model="config.mode">
                <el-radio :value="INTERVIEW_MODE.FULL">全流程面试</el-radio>
                <el-radio :value="INTERVIEW_MODE.STAGE">阶段练习</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="isStageMode" label="选择阶段">
              <el-checkbox-group v-model="config.selectedStages">
                <el-checkbox v-for="stage in STAGES" :key="stage" :label="stage" :value="stage" />
              </el-checkbox-group>
              <p class="stage-hint" v-if="!config.selectedStages.length">请至少选择一个阶段</p>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="startLoading"
                :disabled="!config.position || (isStageMode && !config.selectedStages.length)"
                size="large"
                @click="handleStartInterview"
                style="min-width: 160px"
              >
                开始面试
              </el-button>
            </el-form-item>
          </el-form>
        </section>
      </template>

      <!-- Active Interview Banner -->
      <section class="card active-banner" v-if="activeInterviewId" @click="continueInterview">
        <div class="banner-content">
          <span class="banner-dot" />
          <span>进行中的面试 — 剩余 {{ formatRemaining(activeRemaining) }}</span>
          <el-button type="primary" size="small" plain>继续面试</el-button>
        </div>
      </section>

      <!-- History Section -->
      <section class="card history-section">
        <div class="section-header">
          <h3>面试记录</h3>
          <span class="section-hint" v-if="historyTotal">共 {{ historyTotal }} 条，收藏 {{ history.filter(h => h.is_favorited).length }}/5</span>
        </div>
        <div class="history-table-wrap">
          <el-table :data="history" v-loading="historyLoading" style="width: 100%" :show-header="false">
            <el-table-column min-width="140">
              <template #default="{ row }">
                <div class="history-row">
                  <span class="history-position">{{ row.position }}</span>
                  <div class="history-right">
                    <span class="history-meta">{{ row.difficulty }} / {{ row.mode === 'full' ? '全流程' : '阶段' }}</span>
                    <el-tag :type="statusConfig(row.status).type" size="small" class="history-status-tag">
                      {{ statusConfig(row.status).text }}
                    </el-tag>
                    <span class="history-score" :class="{ pass: row.passed, fail: row.passed != null && !row.passed }">{{ row.overall_score != null ? row.overall_score : '' }}</span>
                    <div class="history-actions">
                    <span class="history-time">{{ formatTime(row.created_at) }}</span>
                    <el-button v-if="row.status === 'completed'" text size="small" type="primary" @click="viewReport(row.interview_id)">报告</el-button>
                    <el-button text size="small" @click="toggleFav(row)" :type="row.is_favorited ? 'warning' : ''">
                      {{ row.is_favorited ? '★' : '☆' }}
                    </el-button>
                    <el-button text size="small" type="danger" @click="deleteInterviewItem(row)">删除</el-button>
                  </div>
                  </div>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="history-pagination" v-if="historyTotal > pageSize">
          <el-pagination
            layout="prev, pager, next"
            :total="historyTotal"
            :page-size="pageSize"
            :current-page="historyPage"
            @current-change="loadHistory"
            size="small"
          />
        </div>
        <el-empty v-if="!historyLoading && !history.length" description="暂无面试记录" :image-size="60" />
      </section>
    </div>

    <!-- Full-screen Parsing Overlay -->
    <div class="parsing-overlay" v-if="uploadState === 'parsing'">
      <div class="parsing-card">
        <el-icon class="parsing-icon" :size="36"><Loading /></el-icon>
        <p class="parsing-title">正在解析简历，请稍候...</p>
        <p class="parsing-hint">AI正在读取并结构化您的简历信息</p>
        <div class="parsing-progress-bar">
          <div class="parsing-progress-inner"></div>
        </div>
      </div>
    </div>

    <!-- Guide Card -->
    <GuideCard />
  </div>
</template>

<style scoped>
.dashboard-page {
  padding: 32px 24px 48px;
}
.page-container {
  max-width: 720px;
  margin: 0 auto;
}
.page-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
  text-align: center;
}
.page-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
  text-align: center;
}

/* Sections */
.card {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 24px;
  margin-bottom: 16px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 4px;
}
.section-header h3 {
  font-size: 15px;
  font-weight: 500;
  color: var(--color-text);
}
.header-actions {
  display: flex;
  align-items: center;
}
.section-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
}

/* Upload */
.upload-area {
  width: 100%;
}
.upload-icon {
  color: var(--color-accent);
}
.upload-text p {
  margin-top: 8px;
  font-size: 14px;
  color: var(--color-text);
}
.upload-text em {
  color: var(--color-accent);
  font-style: normal;
}
.upload-formats {
  font-size: 12px !important;
  color: var(--color-text-secondary) !important;
  margin-top: 4px !important;
}
.progress-bar {
  margin-top: 16px;
}
.progress-text {
  text-align: center;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 8px;
}
.upload-error {
  margin-top: 16px;
}
.quick-start-hint {
  text-align: center;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-light);
}
.divider-text {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-right: 8px;
}

/* Resume Summary */
.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.summary-item .label {
  font-size: 12px;
  color: var(--color-text-secondary);
}
.summary-item .value {
  font-size: 13px;
  color: var(--color-text);
}
.summary-item.skills .value {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* Config */
.config-section {
  /* inherits .card */
}
.stage-hint {
  font-size: 12px;
  color: var(--color-warning);
  margin-top: 6px;
}

/* Active Banner */
.active-banner {
  cursor: pointer;
  border-left: 3px solid var(--color-accent);
  transition: background 0.2s;
}
.active-banner:hover { background: rgba(43, 58, 103, 0.03); }
.banner-content {
  display: flex; align-items: center; gap: 12px;
}
.banner-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #67C23A; flex-shrink: 0; animation: blink 1.5s step-end infinite;
}

/* History */
.history-section .section-header .section-hint { font-size: 12px; color: var(--color-text-secondary); }
.history-row { display: flex; align-items: baseline; gap: 8px; width: 100%; }
.history-position { font-size: 13px; color: var(--color-text); font-weight: 500; flex: 0 0 130px; }
.history-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.history-meta { font-size: 11px; color: var(--color-text-secondary); flex: 0 0 80px; text-align: right; }
.history-status-tag { flex-shrink: 0; }
.history-score { font-size: 13px; font-weight: 600; flex: 0 0 28px; text-align: center; }
.history-actions { display: flex; align-items: center; gap: 4px; flex: 0 0 220px; justify-content: flex-end; }
.history-score.pass { color: var(--color-success); }
.history-score.fail { color: var(--color-error); }
.history-time { font-size: 11px; color: var(--color-text-secondary); }
.history-pagination { display: flex; justify-content: center; margin-top: 12px; }

/* History — Card layout */
.fav-header {
  font-size: 13px; font-weight: 600; color: var(--color-accent);
  padding: 12px 0 8px; border-bottom: 1px solid var(--color-border-light);
  margin-bottom: 10px;
}
.fav-header:first-child { padding-top: 0; }
.history-cards { display: flex; flex-direction: column; gap: 10px; }
.history-card {
  padding: 12px; border: 1px solid var(--color-border-light);
  border-radius: 4px; background: var(--color-card);
  display: flex; flex-direction: column; gap: 6px;
}
.history-card.favorited { border-color: rgba(217, 163, 74, 0.3); background: rgba(217, 163, 74, 0.04); }
.hc-top { display: flex; align-items: center; gap: 8px; }
.hc-star { color: #D9A34A; font-size: 14px; }
.hc-position { font-size: 14px; font-weight: 500; color: var(--color-text); flex: 1; }
.hc-mid { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--color-text-secondary); flex-wrap: wrap; }
.hc-score { font-weight: 600; }
.hc-score.pass { color: var(--color-success); }
.hc-score.fail { color: var(--color-error); }
.hc-time { margin-left: auto; }
.hc-actions { display: flex; gap: 8px; }
.history-pagination { display: flex; justify-content: center; margin-top: 12px; }

/* Parsing Overlay */
.parsing-overlay {
  position: fixed;
  inset: 0;
  background: rgba(255, 255, 255, 0.92);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.parsing-card {
  text-align: center;
  padding: 48px;
}
.parsing-icon {
  color: var(--color-accent);
  animation: spin 1.2s linear infinite;
  margin-bottom: 20px;
}
.parsing-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 8px;
}
.parsing-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
}
.parsing-progress-bar {
  width: 240px;
  height: 3px;
  background: var(--color-border-light);
  border-radius: 2px;
  margin: 0 auto;
  overflow: hidden;
}
.parsing-progress-inner {
  height: 100%;
  width: 30%;
  background: var(--color-accent);
  border-radius: 2px;
  animation: parse-slide 1.6s ease-in-out infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@keyframes parse-slide {
  0% { transform: translateX(-100%); }
  50% { transform: translateX(280%); }
  100% { transform: translateX(-100%); }
}
/* Title visibility */
.title-history { display: none; }

/* ── Mobile (≤768px) ── */
@media (max-width: 768px) {
  .dashboard-page {
    padding: 16px 12px 48px;
  }

  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .summary-grid {
    grid-template-columns: 1fr;
  }

  .history-row {
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }

  .history-position {
    flex: auto;
    font-size: 14px;
    font-weight: 600;
  }

  .history-right {
    flex: auto;
    margin-left: 0;
    flex-wrap: wrap;
    gap: 8px;
  }

  .history-meta {
    flex: auto;
    text-align: left;
    width: auto;
  }

  .history-status-tag {
    flex: auto;
  }

  .history-score {
    flex: auto;
    width: auto;
  }

  .history-actions {
    flex: auto;
    width: 100%;
    justify-content: flex-start;
  }

  .history-table-wrap {
    overflow-x: auto;
  }

  .parsing-card {
    padding: 24px 20px;
    margin: 0 16px;
  }

  /* History view on mobile: show history title + cards, hide upload/config */
  .dashboard-page.view-history .title-default,
  .dashboard-page.view-history .upload-section,
  .dashboard-page.view-history .config-section,
  .dashboard-page.view-history .resume-summary { display: none; }
  .dashboard-page.view-history .title-history { display: block; }

  /* Default view on mobile: hide history section, show upload/config */
  .dashboard-page:not(.view-history) .history-section { display: none; }
  .dashboard-page:not(.view-history) .title-history { display: none; }
  .dashboard-page:not(.view-history) .title-default { display: block; }
}
</style>
