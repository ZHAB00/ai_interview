<script setup>
import { reactive, ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getQuestions, createQuestion, updateQuestion, deleteQuestion } from '../../services/adminService.js'
import { STAGES, DIFFICULTY_MAP, QUESTION_TYPES, DIMENSIONS } from '../../utils/constants.js'

// --- State ---
const loading = ref(false)
const list = ref([])
const total = ref(0)
const pagination = reactive({ page: 1, pageSize: 20 })
const filters = reactive({
  stage: '',
  position: '',
  difficulty: '',
  type: ''
})

// Dialog
const dialogVisible = ref(false)
const dialogTitle = ref('新增题目')
const saving = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const form = reactive({
  stage: '技术面',
  position_tags: [],
  difficulty: '中级',
  type: QUESTION_TYPES.TECHNICAL,
  question_text: '',
  dimensions: [],
  scoring_points: [],
  sample_answer: '',
  follow_up_hints: [],
  tags: []
})

// Scoring points sub-form
const scoringPointInput = reactive({ point: '', max_score: '' })
const editingScoringIndex = ref(-1)

const typeOptions = [
  { label: '技术题', value: QUESTION_TYPES.TECHNICAL },
  { label: '行为题', value: QUESTION_TYPES.BEHAVIORAL },
  { label: '情境题', value: QUESTION_TYPES.SITUATIONAL }
]

const difficultyOptions = ['初级', '中级', '高级']

// --- Load ---
async function loadList() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize
    }
    if (filters.stage) params.stage = filters.stage
    if (filters.position) params.position = filters.position
    if (filters.difficulty) params.difficulty = filters.difficulty
    if (filters.type) params.type = filters.type

    const { data } = await getQuestions(params)
    list.value = data.items || []
    total.value = data.total || 0
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

function handleFilter() {
  pagination.page = 1
  loadList()
}

function handlePageChange(page) {
  pagination.page = page
  loadList()
}

// --- Dialog ---
function resetForm() {
  editingId.value = null
  form.stage = '技术面'
  form.position_tags = []
  form.difficulty = '中级'
  form.type = QUESTION_TYPES.TECHNICAL
  form.question_text = ''
  form.dimensions = []
  form.scoring_points = []
  form.sample_answer = ''
  form.follow_up_hints = []
  form.tags = []
  editingScoringIndex.value = -1
  scoringPointInput.point = ''
  scoringPointInput.max_score = ''
}

function openCreate() {
  resetForm()
  dialogTitle.value = '新增题目'
  dialogVisible.value = true
}

function openEdit(row) {
  resetForm()
  dialogTitle.value = '编辑题目'
  editingId.value = row.id
  Object.assign(form, {
    stage: row.stage || '技术面',
    position_tags: row.position_tags || [],
    difficulty: row.difficulty || '中级',
    type: row.type || QUESTION_TYPES.TECHNICAL,
    question_text: row.question_text || '',
    dimensions: row.dimensions || [],
    scoring_points: JSON.parse(JSON.stringify(row.scoring_points || [])),
    sample_answer: row.sample_answer || '',
    follow_up_hints: row.follow_up_hints || [],
    tags: row.tags || []
  })
  dialogVisible.value = true
}

async function handleSave() {
  saving.value = true
  try {
    const payload = { ...form }
    if (editingId.value) {
      await updateQuestion(editingId.value, payload)
      ElMessage.success('题目已更新')
    } else {
      await createQuestion(payload)
      ElMessage.success('题目已创建')
    }
    dialogVisible.value = false
    loadList()
  } catch (err) {
    ElMessage.error(err.response?.data?.error?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定删除该题目吗？删除后历史报告不受影响', '删除确认', {
      type: 'warning',
      confirmButtonText: '确定删除',
      cancelButtonText: '取消'
    })
    await deleteQuestion(row.id)
    ElMessage.success('题目已删除')
    loadList()
  } catch {
    // cancelled
  }
}

// --- Scoring Points ---
function addScoringPoint() {
  if (!scoringPointInput.point || !scoringPointInput.max_score) return
  form.scoring_points.push({
    point: scoringPointInput.point,
    max_score: parseInt(scoringPointInput.max_score) || 0
  })
  scoringPointInput.point = ''
  scoringPointInput.max_score = ''
}

function removeScoringPoint(idx) {
  form.scoring_points.splice(idx, 1)
}

// --- Computed ---
const stageOptions = computed(() => STAGES)
const questionTypeLabel = (type) => {
  const found = typeOptions.find(t => t.value === type)
  return found ? found.label : type
}
const questionTextSummary = (text) => {
  if (!text) return ''
  return text.length > 40 ? text.slice(0, 40) + '...' : text
}
const tagList = (val) => {
  if (Array.isArray(val)) return val
  if (typeof val === 'string') {
    try { return JSON.parse(val) } catch { return [val] }
  }
  return []
}

onMounted(loadList)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <h1>题库管理</h1>
      <el-button type="primary" @click="openCreate">新增题目</el-button>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <el-select v-model="filters.stage" placeholder="阶段" clearable size="small" style="width: 120px">
        <el-option v-for="s in stageOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <el-select v-model="filters.difficulty" placeholder="难度" clearable size="small" style="width: 100px">
        <el-option v-for="d in difficultyOptions" :key="d" :label="d" :value="d" />
      </el-select>
      <el-select v-model="filters.type" placeholder="题型" clearable size="small" style="width: 110px">
        <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-input v-model="filters.position" placeholder="岗位关键词" clearable size="small" style="width: 160px" />
      <el-button size="small" @click="handleFilter">筛选</el-button>
    </div>

    <!-- Table -->
    <el-table :data="list" v-loading="loading" style="width: 100%">
      <el-table-column label="阶段" prop="stage" width="80" />
      <el-table-column label="岗位标签" min-width="140">
        <template #default="{ row }">
          <el-tag v-for="tag in tagList(row.position_tags)" :key="tag" size="small" type="info" style="margin-right: 4px">
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="难度" prop="difficulty" width="60" />
      <el-table-column label="题型" width="80">
        <template #default="{ row }">{{ questionTypeLabel(row.type) }}</template>
      </el-table-column>
      <el-table-column label="题目" min-width="200">
        <template #default="{ row }">{{ questionTextSummary(row.question_text) }}</template>
      </el-table-column>
      <el-table-column label="标签" min-width="120">
        <template #default="{ row }">
          <el-tag v-for="tag in tagList(row.tags)" :key="tag" size="small" style="margin-right: 4px">
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button text size="small" @click="openEdit(row)">编辑</el-button>
          <el-button text size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div class="pagination-wrap" v-if="total > pagination.pageSize">
      <el-pagination
        v-model:current-page="pagination.page"
        :page-size="pagination.pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="680px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" label-position="top">
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="阶段">
              <el-select v-model="form.stage" style="width: 100%">
                <el-option v-for="s in stageOptions" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="难度">
              <el-select v-model="form.difficulty" style="width: 100%">
                <el-option v-for="d in difficultyOptions" :key="d" :label="d" :value="d" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="题型">
              <el-select v-model="form.type" style="width: 100%">
                <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="题目内容">
          <el-input v-model="form.question_text" type="textarea" :rows="3" placeholder="请输入题目内容" />
        </el-form-item>

        <el-form-item label="考察维度">
          <el-checkbox-group v-model="form.dimensions">
            <el-checkbox v-for="dim in DIMENSIONS" :key="dim" :label="dim" :value="dim" />
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="岗位标签">
          <el-select v-model="form.position_tags" multiple filterable allow-create placeholder="输入岗位名称后回车添加" style="width: 100%" />
        </el-form-item>

        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple filterable allow-create placeholder="输入标签后回车添加" style="width: 100%" />
        </el-form-item>

        <!-- Scoring Points -->
        <el-form-item label="评分要点">
          <div class="scoring-points-list">
            <div v-for="(sp, idx) in form.scoring_points" :key="idx" class="sp-row">
              <span class="sp-point">{{ sp.point }}</span>
              <span class="sp-score">{{ sp.max_score }}分</span>
              <el-button text size="small" type="danger" @click="removeScoringPoint(idx)">删除</el-button>
            </div>
          </div>
          <div class="sp-add">
            <el-input v-model="scoringPointInput.point" placeholder="评分要点描述" size="small" style="width: 280px" />
            <el-input v-model.number="scoringPointInput.max_score" placeholder="分值" size="small" style="width: 80px" />
            <el-button size="small" @click="addScoringPoint">添加</el-button>
          </div>
        </el-form-item>

        <el-form-item label="参考答案">
          <el-input v-model="form.sample_answer" type="textarea" :rows="3" placeholder="参考答案（可选）" />
        </el-form-item>

        <el-form-item label="追问方向">
          <el-select v-model="form.follow_up_hints" multiple filterable allow-create placeholder="输入追问方向后回车添加" style="width: 100%" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">
          {{ editingId ? '保存修改' : '创建题目' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.admin-page {
  padding: 24px;
  background: var(--color-bg);
  min-height: calc(100vh - 48px - 38px);
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-header h1 {
  font-size: 20px;
  font-weight: 600;
}
.filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}

/* Scoring Points */
.scoring-points-list {
  margin-bottom: 10px;
}
.sp-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px;
  background: var(--color-border-light);
  border-radius: 2px;
  margin-bottom: 4px;
  font-size: 13px;
}
.sp-point { flex: 1; color: var(--color-text); }
.sp-score { font-weight: 500; color: var(--color-accent); flex-shrink: 0; }
.sp-add {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
