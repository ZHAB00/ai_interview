<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { uploadDocument, getDocuments, deleteDocument, reprocessDocument } from '../../services/adminService.js'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
let pollTimer = null

const form = reactive({
  description: '',
  tags: ''
})
const uploadFileList = ref([])

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
      currentPage.value = 1
      loadList()
    })
    .catch(err => {
      ElMessage.error(err.response?.data?.error?.message || '上传失败')
    })
    .finally(() => { saving.value = false })
}

async function loadList() {
  loading.value = true
  try {
    const { data } = await getDocuments({ page: currentPage.value, page_size: pageSize.value })
    list.value = data.items || []
    total.value = data.total || 0
  } catch {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm('确定删除该文档吗？FAISS 向量索引将同步清除', '删除确认', {
      type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消'
    })
    await deleteDocument(row.id)
    ElMessage.success('文档已删除')
    currentPage.value = 1
    loadList()
  } catch {}
}

async function handleReprocess(row) {
  try {
    await reprocessDocument(row.id)
    ElMessage.success('已提交重新处理')
    row.status = 'processing'
    startPolling()
  } catch (err) {
    ElMessage.error(err.response?.data?.error?.message || '重处理失败')
  }
}

function hasProcessing() {
  return list.value.some(d => d.status === 'processing')
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!hasProcessing()) {
      stopPolling()
      return
    }
    try {
      const { data } = await getDocuments({ page: currentPage.value, page_size: pageSize.value })
      list.value = data.items || []
      total.value = data.total || 0
    } catch {}
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onPageChange(page) {
  currentPage.value = page
  loadList()
}

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

onMounted(async () => {
  await loadList()
  if (hasProcessing()) startPolling()
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <div class="admin-mobile-nav">
        <router-link to="/admin/questions" class="am-nav">题库管理</router-link>
        <router-link to="/admin/documents" class="am-nav active">文档管理</router-link>
      </div>
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
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row }">
          <el-button v-if="row.status === 'error'" text size="small" type="warning" @click="handleReprocess(row)">
            重处理
          </el-button>
          <el-button text size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > pageSize" style="display: flex; justify-content: center; margin-top: 16px;">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="onPageChange"
      />
    </div>

    <el-empty v-if="!loading && !list.length" description="暂无文档" />

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
.admin-mobile-nav { display: none; }
@media (max-width: 768px) {
  .admin-page { padding: 12px 10px 60px; }
  .admin-mobile-nav { display: flex; gap: 0; margin-bottom: 12px; border-radius: 4px; overflow: hidden; border: 1px solid var(--color-border); }
  .am-nav { flex: 1; text-align: center; padding: 8px 0; font-size: 13px; color: var(--color-text-secondary); background: var(--color-card); text-decoration: none; }
  .am-nav.active { color: var(--color-accent); background: rgba(43,58,103,0.06); font-weight: 500; }
}
</style>
