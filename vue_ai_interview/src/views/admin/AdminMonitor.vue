<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../services/api.js'

const router = useRouter()

// --- State ---
const activeTab = ref('users')
const users = ref([])
const interviews = ref([])
const summary = ref({ online_users: 0, total_users: 0, active_interviews: 0, total_interviews: 0 })
const loading = ref(false)
const countdown = ref(5)

let pollTimer = null
let countdownTimer = null

// --- Polling ---
async function fetchData() {
  loading.value = true
  try {
    const [summaryRes, dataRes] = await Promise.all([
      api.get('/api/admin/monitor/summary'),
      api.get(activeTab.value === 'users'
        ? '/api/admin/monitor/users'
        : '/api/admin/monitor/interviews'
      ),
    ])
    summary.value = summaryRes.data
    if (activeTab.value === 'users') {
      users.value = dataRes.data.items || []
    } else {
      interviews.value = dataRes.data.items || []
    }
  } catch (err) {
    if (err.response?.status === 401 || err.response?.status === 403) {
      router.push('/dashboard')
    }
  } finally {
    loading.value = false
  }
}

function startPolling() {
  fetchData()
  countdown.value = 5
  countdownTimer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) countdown.value = 5
  }, 1000)
  pollTimer = setInterval(() => {
    fetchData()
    countdown.value = 5
  }, 5000)
}

function stopPolling() {
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
}

function switchTab(tab) {
  activeTab.value = tab
  fetchData()
  countdown.value = 5
}

onMounted(startPolling)
onUnmounted(stopPolling)

// --- Helpers ---
function formatDuration(seconds) {
  if (seconds == null) return '-'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}分${s}秒` : `${s}秒`
}

function formatTime(dt) {
  if (!dt) return '-'
  const d = new Date(dt)
  const now = new Date()
  const diffMs = now - d
  if (diffMs < 86400000) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

function statusLabel(status) {
  const map = { created: '待开始', in_progress: '进行中', completed: '已完成', abandoned: '已放弃' }
  return map[status] || status
}

function statusClass(status) {
  return 'status-' + status
}

const isMobile = computed(() => window.innerWidth <= 768)
</script>

<template>
  <div class="monitor-page">
    <!-- Summary Bar -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-num online">{{ summary.online_users }}</span>
        <span class="summary-label">在线用户</span>
        <span class="summary-div">/ {{ summary.total_users }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-num active">{{ summary.active_interviews }}</span>
        <span class="summary-label">进行中面试</span>
        <span class="summary-div">/ {{ summary.total_interviews }}</span>
      </div>
      <div class="summary-item refresh-info">
        <span>下次刷新 {{ countdown }}s</span>
      </div>
    </div>

    <!-- Tab Switcher -->
    <div class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'users' }]"
        @click="switchTab('users')"
      >用户列表</button>
      <button
        :class="['tab-btn', { active: activeTab === 'interviews' }]"
        @click="switchTab('interviews')"
      >面试记录</button>
    </div>

    <!-- Loading -->
    <div v-if="loading && !users.length && !interviews.length" class="loading-state">
      加载中...
    </div>

    <!-- Users Table -->
    <div v-if="activeTab === 'users'" class="table-wrap">
      <!-- Desktop table -->
      <table v-if="!isMobile" class="data-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>角色</th>
            <th>状态</th>
            <th>注册时间</th>
            <th>面试次数</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.user_id">
            <td class="cell-user">{{ u.username }}</td>
            <td><span :class="['role-tag', u.role]">{{ u.role === 'admin' ? '管理员' : '用户' }}</span></td>
            <td>
              <span :class="['status-dot', u.is_online ? 'online' : 'offline']"></span>
              {{ u.is_online ? '在线' : '离线' }}
            </td>
            <td class="cell-time">{{ formatTime(u.created_at) }}</td>
            <td>{{ u.interview_count }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Mobile cards -->
      <div v-else class="card-list">
        <div v-for="u in users" :key="u.user_id" class="data-card">
          <div class="card-row">
            <span class="card-user">{{ u.username }}</span>
            <span :class="['role-tag', u.role]">{{ u.role === 'admin' ? '管理员' : '用户' }}</span>
            <span :class="['status-dot', u.is_online ? 'online' : 'offline']"></span>
            <span :class="u.is_online ? 'text-online' : 'text-offline'">{{ u.is_online ? '在线' : '离线' }}</span>
          </div>
          <div class="card-row card-meta">
            <span>注册: {{ formatTime(u.created_at) }}</span>
            <span>面试 {{ u.interview_count }} 次</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Interviews Table -->
    <div v-if="activeTab === 'interviews'" class="table-wrap">
      <table v-if="!isMobile" class="data-table">
        <thead>
          <tr>
            <th>用户</th>
            <th>岗位</th>
            <th>难度</th>
            <th>阶段</th>
            <th>时长</th>
            <th>连线</th>
            <th>状态</th>
            <th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="iv in interviews" :key="iv.interview_id">
            <td class="cell-user">{{ iv.username }}</td>
            <td>{{ iv.position }}</td>
            <td><span :class="['diff-tag', iv.difficulty]">{{ iv.difficulty }}</span></td>
            <td>{{ iv.current_stage || '-' }}</td>
            <td>{{ formatDuration(iv.duration_seconds) }}</td>
            <td>
              <span :class="['status-dot', iv.is_ws_connected ? 'online' : 'offline']"></span>
              {{ iv.is_ws_connected ? '连线中' : '离线' }}
            </td>
            <td><span :class="['status-tag', statusClass(iv.status)]">{{ statusLabel(iv.status) }}</span></td>
            <td class="cell-time">{{ formatTime(iv.created_at) }}</td>
          </tr>
        </tbody>
      </table>

      <!-- Mobile cards -->
      <div v-else class="card-list">
        <div v-for="iv in interviews" :key="iv.interview_id" class="data-card">
          <div class="card-row">
            <span class="card-user">{{ iv.username }}</span>
            <span :class="['status-tag', statusClass(iv.status)]">{{ statusLabel(iv.status) }}</span>
            <span :class="['status-dot', iv.is_ws_connected ? 'online' : 'offline']"></span>
          </div>
          <div class="card-row">
            <span>{{ iv.position }}</span>
            <span :class="['diff-tag', iv.difficulty]">{{ iv.difficulty }}</span>
          </div>
          <div class="card-row card-meta">
            <span v-if="iv.current_stage">{{ iv.current_stage }}</span>
            <span v-if="iv.duration_seconds != null">{{ formatDuration(iv.duration_seconds) }}</span>
            <span>{{ formatTime(iv.created_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.monitor-page {
  padding: 16px 20px;
  max-width: 1100px;
  margin: 0 auto;
}

/* Summary Bar */
.summary-bar {
  display: flex;
  gap: 24px;
  padding: 12px 16px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.summary-item { display: flex; align-items: baseline; gap: 4px; }
.summary-num { font-size: 22px; font-weight: 700; }
.summary-num.online { color: #22c55e; }
.summary-num.active { color: var(--color-accent); }
.summary-label { font-size: 12px; color: var(--color-text-secondary); }
.summary-div { font-size: 14px; color: var(--color-text-secondary); }
.refresh-info { margin-left: auto; font-size: 11px; color: var(--color-text-secondary); }

/* Tab Bar */
.tab-bar { display: flex; gap: 0; margin-bottom: 12px; }
.tab-btn {
  padding: 6px 20px;
  border: 1px solid var(--color-border);
  background: var(--color-card);
  color: var(--color-text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.tab-btn:first-child { border-radius: 4px 0 0 4px; }
.tab-btn:last-child { border-radius: 0 4px 4px 0; }
.tab-btn.active {
  background: var(--color-accent);
  color: #fff;
  border-color: var(--color-accent);
}

/* Data Table */
.table-wrap { overflow-x: auto; }
.data-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
}
.data-table th {
  background: var(--color-bg);
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--color-text-secondary);
  font-size: 12px;
  border-bottom: 1px solid var(--color-border);
}
.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text);
}
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover { background: rgba(43, 58, 103, 0.02); }

.cell-user { font-weight: 500; }
.cell-time { color: var(--color-text-secondary); font-size: 12px; }

/* Status */
.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 4px;
}
.status-dot.online { background: #22c55e; }
.status-dot.offline { background: #d1d5db; }

.role-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 2px;
}
.role-tag.admin { background: rgba(217, 163, 74, 0.15); color: #b8860b; }
.role-tag.candidate { background: rgba(107, 114, 128, 0.1); color: #6b7280; }

.status-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 2px;
}
.status-in_progress { background: rgba(43, 58, 103, 0.08); color: var(--color-accent); }
.status-completed { background: rgba(34, 197, 94, 0.08); color: #16a34a; }
.status-abandoned { background: rgba(239, 68, 68, 0.08); color: #dc2626; }
.status-created { background: rgba(107, 114, 128, 0.08); color: #6b7280; }

.diff-tag {
  display: inline-block;
  padding: 1px 6px;
  font-size: 11px;
  border-radius: 2px;
  background: rgba(107, 114, 128, 0.08);
  color: #6b7280;
}

.text-online { color: #22c55e; font-size: 12px; }
.text-offline { color: #9ca3af; font-size: 12px; }

/* Loading */
.loading-state {
  text-align: center;
  padding: 40px;
  color: var(--color-text-secondary);
}

/* Mobile Cards */
.card-list { display: flex; flex-direction: column; gap: 8px; }
.data-card {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 10px 12px;
}
.card-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.card-row + .card-row { margin-top: 6px; }
.card-user { font-weight: 600; font-size: 14px; }
.card-meta { font-size: 11px; color: var(--color-text-secondary); gap: 12px; }

/* Mobile */
@media (max-width: 768px) {
  .monitor-page { padding: 10px 8px; }
  .summary-bar { gap: 12px; padding: 8px 12px; }
  .summary-num { font-size: 18px; }
  .refresh-info { margin-left: 0; width: 100%; }
}
</style>
