<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { uploadDocument, getDocuments, deleteDocument } from '../../services/adminService.js'

// --- State ---
const loading = ref(false)
const saving = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const form = reactive({
  description: '',
  tags: ''
})
const uploadFileList = ref([])

// --- Upload ---
function handleUpload() {
  if (!uploadFileList.value.length) return

  const file = uploadFileList.value[0].raw
  const formData = new FormData()
  formData.append('file', file)
  if (form.description) formData.append('description', form.description)
  if (form.tags) formData.append('tags', form.tags)

  saving.value = true
  uploadDocument(formData)
    .then(() => {
      ElMessage.success('文档已上传，正在向量化处理')
      dialogVisible.value = false
      uploadFileList.value = []
      form.description = ''
      form.tags = ''
      loadList()
    })
    .catch(err => {
      ElMessage.error(err.response?.data?.error?.message || '上传失败')
    })
    .finally(() => {
      saving.value = false
    })
}

// --- List ---
async function loadList() {
  loading.value = true
  try {
    const { data } = await getDocuments({ page: 1, page_size: 50 })
    list.value = data.items || []
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

// --- Delete ---
async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定删除该文档吗？FAISS 向量索引将同步清除', '删除确认', {
      type: 'warning',
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    await deleteDocument(row.id)
    ElMessage.success('文档已删除')
    loadList()
  } catch {
    // cancelled
  }
}

// --- Utils ---
function statusConfig(status) {
  const map = {
    processing: { text: '处理中', type: 'warning' },
    ready: { text: '就绪', type: 'success' },
    error: { text: '失败', type: 'danger' }
  }
  return map[status] || { text: status, type: 'info' }
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('zh-CN')
}

function tagList(val) {
  if (Array.isArray(val)) return val
  if (typeof val === 'string') {
    try { return JSON.parse(val) } catch { return val ? [val] : [] }
  }
  return []
}

onMounted(loadList)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <h1>文档管理</h1>
      <el-button type="primary" @click="dialogVisible = true">上传文档</el-button>
    </div>

    <el-table :data="list" v-loading="loading" style="width: 100%">
      <el-table-column label="文件名" prop="filename" min-width="200" />
      <el-table-column label="描述" prop="description" min-width="160">
        <template #default="{ row }">
          <span class="desc-text">{{ row.description || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="标签" min-width="140">
        <template #default="{ row }">
          <el-tag v-for="tag in tagList(row.tags)" :key="tag" size="small" style="margin-right: 4px">
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="切片数" width="80" prop="chunks_count" align="center" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusConfig(row.status).type" size="small">
            {{ statusConfig(row.status).text }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" align="center">
        <template #default="{ row }">
          <el-button text size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !list.length" description="暂无文档" />

    <!-- Upload Dialog -->
    <el-dialog v-model="dialogVisible" title="上传文档" width="480px" :close-on-click-modal="false">
      <el-form :model="form" label-position="top">
        <el-form-item label="选择文件">
          <el-upload
            v-model:file-list="uploadFileList"
            :auto-upload="false"
            :limit="1"
            :accept="'.pdf,.doc,.docx,.txt,.md'"
            drag
          >
            <el-icon :size="32"><UploadFilled /></el-icon>
            <div class="upload-text">拖拽文件到此处，或 <em>点击上传</em></div>
            <template #tip>
              <p class="upload-tip">支持 PDF / Word / TXT / Markdown 格式</p>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item label="文档描述">
          <el-input v-model="form.description" placeholder="可选，简要描述文档内容" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="可选，多个标签用逗号分隔" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!uploadFileList.length" @click="handleUpload">
          上传并处理
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
.desc-text {
  color: var(--color-text-secondary);
}
.upload-text {
  font-size: 13px;
  color: var(--color-text);
  margin-top: 8px;
}
.upload-text em {
  color: var(--color-accent);
  font-style: normal;
}
.upload-tip {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 6px;
}
</style>
