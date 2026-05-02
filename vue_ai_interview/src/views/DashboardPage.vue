<script setup>
import { reactive, ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { uploadResume } from '../services/resumeService.js'
import { createInterview, getInterviewHistory } from '../services/interviewService.js'
import { STAGES, INTERVIEW_MODE } from '../utils/constants.js'
import GuideCard from '../components/GuideCard.vue'
import { steps } from '../components/GuideCard.vue'

const router = useRouter()

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
async function loadHistory() {
  historyLoading.value = true
  try {
    const { data } = await getInterviewHistory(1, 5)
    history.value = data.items || []
  } catch {
    history.value = []
  } finally {
    historyLoading.value = false
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

onMounted(() => {
  loadHistory()
})

// Expose steps for GuideCard template
const guideSteps = steps
</script>

<template>
  <div class="dashboard-page">
    <div class="page-container">
      <h1 class="page-title">面试控制台</h1>
      <p class="page-desc">上传简历，配置面试参数，开始您的模拟面试练习</p>

      <!-- Resume Upload Section -->
      <section class="card upload-section" v-if="uploadState !== 'done'">
        <div class="section-header">
          <h3>第一步：上传简历</h3>
          <span class="section-hint">支持 PDF、Word、图片格式，最大 10MB</span>
        </div>

        <el-upload
          ref="uploadRef"
          class="upload-area"
          drag
          :auto-upload="false"
          :limit="1"
          :on-change="handleFileChange"
          :accept="'.pdf,.docx,.jpg,.jpeg,.png'"
          :show-file-list="false"
          :disabled="uploadState === 'uploading' || uploadState === 'parsing'"
        >
          <el-icon class="upload-icon" :size="40"><UploadFilled /></el-icon>
          <div class="upload-text">
            <p>拖拽文件到此处，或 <em>点击上传</em></p>
            <p class="upload-formats">PDF / DOCX / JPG / PNG</p>
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

      <!-- History Section -->
      <section class="card history-section">
        <div class="section-header">
          <h3>最近面试记录</h3>
          <span class="section-hint" v-if="history.length">最近 5 条</span>
        </div>
        <el-table :data="history" v-loading="historyLoading" style="width: 100%" :show-header="false">
          <el-table-column label="岗位" min-width="160">
            <template #default="{ row }">
              <span class="history-position">{{ row.position }}</span>
              <span class="history-meta">{{ row.difficulty }} / {{ row.mode === 'full' ? '全流程' : '阶段' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="statusConfig(row.status).type" size="small">
                {{ statusConfig(row.status).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170" align="right">
            <template #default="{ row }">
              <span class="history-time">{{ formatTime(row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" align="center">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'completed'"
                text
                type="primary"
                size="small"
                @click="viewReport(row.interview_id)"
              >
                查看报告
              </el-button>
            </template>
          </el-table-column>
        </el-table>
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
}
.page-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
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

/* History */
.history-position {
  display: block;
  font-size: 13px;
  color: var(--color-text);
}
.history-meta {
  font-size: 11px;
  color: var(--color-text-secondary);
}
.history-time {
  font-size: 12px;
  color: var(--color-text-secondary);
}

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
</style>
