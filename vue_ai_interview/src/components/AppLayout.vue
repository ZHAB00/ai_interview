<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTheme } from '../composables/useTheme.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/authStore.js'
import { useInterviewStore } from '../stores/interviewStore.js'
import NetworkStatus from './NetworkStatus.vue'
import { ETHICS_STATEMENT } from '../utils/constants.js'
import api from '../services/api.js'
import { getActiveInterview } from '../services/interviewService.js'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const interviewStore = useInterviewStore()
const { theme: currentTheme, setTheme } = useTheme()

// Reactive mobile detection
const windowWidth = ref(window.innerWidth)
function onResize() { windowWidth.value = window.innerWidth }
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
const isMobile = computed(() => windowWidth.value <= 768)

const themeLabel = computed(() => {
  const m = { light: '浅色', dark: '深色', warm: '暖色' }
  return m[currentTheme.value] || '浅色'
})

const isInterviewActive = computed(() =>
  interviewStore.status === 'in_progress'
)

// --- Bottom Tab ---
const hasActiveInterview = ref(false)
const activeInterviewId = ref(null)

async function checkActive() {
  try {
    const { data } = await getActiveInterview()
    hasActiveInterview.value = data.active
    activeInterviewId.value = data.interview_id
  } catch { /* ignore */ }
}
onMounted(checkActive)

const tabs = computed(() => {
  const items = [
    { key: 'dashboard', label: '首页', icon: 'HomeFilled', activeIcon: 'HomeFilled', path: '/dashboard' },
    { key: 'interview', label: '面试', icon: 'Mic', activeIcon: 'Mic', path: isInterviewActive.value ? route.path : '/dashboard' },
    { key: 'messages', label: '留言', icon: 'ChatDotRound', activeIcon: 'ChatDotSquare', path: '/messages' },
    { key: 'report', label: '报告', icon: 'Document', activeIcon: 'DataAnalysis', path: '/dashboard' },
  ]
  if (authStore.isAdmin) {
    items.push({ key: 'admin', label: '管理', icon: 'Setting', activeIcon: 'Setting', path: adminTabSub.value === 'questions' ? '/admin/questions' : '/admin/documents' })
  }
  return items
})

const activeTab = computed(() => {
  const p = route.path
  if (p.startsWith('/interview')) return 'interview'
  if (p.startsWith('/messages')) return 'messages'
  if (p.startsWith('/report')) return 'report'
  if (p.startsWith('/admin')) return 'admin'
  if (p === '/dashboard' && route.query.view === 'history') return 'report'
  return 'dashboard'
})

const isOnInterviewPage = computed(() => route.path.startsWith('/interview'))

async function goTab(tab) {
  // Interview tab: go back to active interview
  if (tab.key === 'interview') {
    if (isOnInterviewPage.value) return // already there
    await checkActive()  // refresh — may have changed since mount
    if (hasActiveInterview.value) {
      router.push(`/interview/${activeInterviewId.value}`)
      return
    }
    ElMessage.info('暂无进行中的面试，请先上传简历创建面试')
    return
  }

  // Leaving interview page: confirm before navigating away
  if (isOnInterviewPage.value && isInterviewActive.value) {
    ElMessageBox.confirm('正在面试中，确定离开吗？', '提示', { confirmButtonText: '离开', cancelButtonText: '继续面试', type: 'warning' })
      .then(() => router.push(tab.path))
      .catch(() => {})
    return
  }

  // Report tab — show history list
  if (tab.key === 'report') {
    router.push('/dashboard?view=history')
    return
  }

  // Messages tab
  if (tab.key === 'messages') {
    router.push('/messages')
    return
  }

  // Admin tab — toggle between questions and documents
  if (tab.key === 'admin') {
    if (activeTab.value === 'admin') {
      adminTabSub.value = adminTabSub.value === 'questions' ? 'documents' : 'questions'
    }
    router.push(adminTabSub.value === 'questions' ? '/admin/questions' : '/admin/documents')
    return
  }

  router.push(tab.path)
}

// --- Invite Code ---
const adminTabSub = ref('questions')
const inviteDialog = ref(false)
const inviteCode = ref('')
const countdown = ref('')
let countdownTimer = null

function calcRemaining() {
  const now = new Date()
  const min = now.getUTCMinutes()
  const sec = now.getUTCSeconds()
  const quarter = Math.floor(min / 15)
  const nextMin = (quarter + 1) * 15
  let diffMin = nextMin - min
  if (diffMin >= 15) diffMin -= 15
  const totalSec = diffMin * 60 - sec
  if (totalSec <= 0) return '刷新中...'
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}分${s.toString().padStart(2, '0')}秒后刷新`
}

async function fetchInviteCode() {
  try {
    const { data } = await api.get('/api/auth/invite-code')
    inviteCode.value = data.invite_code
    countdown.value = calcRemaining()
  } catch (err) {
    inviteCode.value = err.response?.status === 401 ? '请重新登录' : '获取失败'
  }
}

function openInviteDialog() {
  fetchInviteCode()
  fetchTimedCodes()
  inviteDialog.value = true
  clearInterval(countdownTimer)
  countdownTimer = setInterval(() => {
    const cd = calcRemaining()
    if (cd === '刷新中...') {
      fetchInviteCode()
    } else {
      countdown.value = cd
    }
  }, 1000)
}

function closeInviteDialog() {
  inviteDialog.value = false
  clearInterval(countdownTimer)
}

function copyInviteCode() {
  navigator.clipboard.writeText(inviteCode.value).then(() => {
    ElMessage.success('邀请码已复制')
  })
}

// --- Timed Invite Codes ---
const timedCodes = ref([])
const duration = ref(2)
const maxUses = ref(5)
const generating = ref(false)

const durationOptions = [
  { label: '30分钟', value: 0.5 },
  { label: '1小时', value: 1 },
  { label: '2小时', value: 2 },
  { label: '6小时', value: 6 },
  { label: '12小时', value: 12 },
  { label: '1天', value: 24 },
  { label: '3天', value: 72 },
  { label: '7天', value: 168 },
  { label: '30天', value: 720 },
]

const maxUsesOptions = [
  { label: '1次', value: 1 },
  { label: '3次', value: 3 },
  { label: '5次', value: 5 },
  { label: '10次', value: 10 },
  { label: '50次', value: 50 },
  { label: '不限', value: 0 },
]

async function fetchTimedCodes() {
  try {
    const { data } = await api.get('/api/admin/invite-codes')
    timedCodes.value = data.items || []
  } catch { timedCodes.value = [] }
}

async function generateTimedCode() {
  generating.value = true
  try {
    await api.post('/api/admin/invite-codes', {
      duration_hours: duration.value,
      max_uses: maxUses.value || null,
    })
    ElMessage.success('邀请码已生成')
    await fetchTimedCodes()
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '生成失败')
  } finally {
    generating.value = false
  }
}

async function copyTimedCode(code) {
  await navigator.clipboard.writeText(code)
  ElMessage.success('邀请码已复制')
}

async function deactivateTimedCode(id) {
  try {
    await api.delete(`/api/admin/invite-codes/${id}`)
    ElMessage.success('邀请码已删除')
    await fetchTimedCodes()
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '删除失败')
  }
}

function isExpired(c) {
  return new Date(c.expires_at) < new Date()
}

function isExhausted(c) {
  return c.max_uses !== null && c.use_count >= c.max_uses
}

function codeStatus(c) {
  if (!c.is_active) return '已停用'
  if (isExpired(c)) return '已过期'
  if (isExhausted(c)) return '已用完'
  if (c.max_uses) return `${c.use_count}/${c.max_uses}次`
  return `${c.use_count}次使用`
}

function expiresFormat(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const m = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${m}-${day} ${h}:${min}到期`
}

onUnmounted(() => clearInterval(countdownTimer))

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="header-left">
        <span class="logo" @click="router.push('/dashboard')">AI面试官</span>
        <span v-if="isInterviewActive" class="stage-tag">
          {{ interviewStore.currentStage }}
        </span>
      </div>
      <div class="header-right">
        <NetworkStatus v-if="isInterviewActive" />
        <span class="invite-link desktop-only" @click="router.push('/messages')">留言板</span>
        <span v-if="authStore.isAdmin" class="invite-link" @click="openInviteDialog">邀请码</span>
        <el-dropdown trigger="click" v-if="authStore.isLoggedIn">
          <el-icon class="theme-btn" :size="20"><Brush /></el-icon>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="setTheme('light')" :class="{ 'theme-active': currentTheme === 'light' }">☀️ 浅色</el-dropdown-item>
              <el-dropdown-item @click="setTheme('dark')" :class="{ 'theme-active': currentTheme === 'dark' }">🌙 深色</el-dropdown-item>
              <el-dropdown-item @click="setTheme('warm')" :class="{ 'theme-active': currentTheme === 'warm' }">🔥 暖色</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click" v-if="authStore.isLoggedIn">
          <span class="user-info">
            {{ authStore.username || '用户' }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="!isMobile" @click="router.push('/dashboard')">首页</el-dropdown-item>
              <el-dropdown-item v-if="authStore.isAdmin && !isMobile" @click="router.push('/admin/questions')">题库管理</el-dropdown-item>
              <el-dropdown-item v-if="authStore.isAdmin && !isMobile" @click="router.push('/admin/documents')">文档管理</el-dropdown-item>
              <el-dropdown-item :divided="!isMobile" @click="handleLogout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <main class="app-content">
      <router-view />
    </main>

    <footer class="app-footer">
      {{ ETHICS_STATEMENT }}
    </footer>

    <!-- Bottom Tab Bar (mobile only) -->
    <nav class="bottom-tabs">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeTab === tab.key }"
        @click="goTab(tab)"
      >
        <el-icon :size="20"><component :is="activeTab === tab.key ? tab.activeIcon : tab.icon" /></el-icon>
        <span class="tab-label">{{ tab.label }}</span>
      </div>
    </nav>

    <!-- Invite Code Dialog -->
    <el-dialog v-model="inviteDialog" title="内测邀请码" width="380px" :close-on-click-modal="false" @close="closeInviteDialog" class="invite-dialog">
      <div class="invite-dialog-body">
        <!-- Section 1: rotating code -->
        <div class="invite-section">
          <div class="invite-section-title">动态轮换码</div>
          <div class="invite-code-display">{{ inviteCode }}</div>
          <div class="invite-countdown">
            <span class="countdown-dot" />
            {{ countdown }}
          </div>
          <div class="invite-actions">
            <el-button type="primary" size="small" @click="copyInviteCode">复制邀请码</el-button>
            <el-button size="small" text @click="fetchInviteCode">立即刷新</el-button>
          </div>
          <p class="invite-tip">同一窗口内上一个码也有效（15分钟容错）</p>
        </div>

        <el-divider />

        <!-- Section 2: timed codes -->
        <div class="invite-section">
          <div class="invite-section-title">生成限时邀请码</div>
          <div class="timed-form">
            <div class="timed-form-item">
              <label>有效期</label>
              <el-select v-model="duration" size="small" popper-class="invite-popper" teleported style="width: 90px">
                <el-option v-for="o in durationOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
            <div class="timed-form-item">
              <label>次数</label>
              <el-select v-model="maxUses" size="small" popper-class="invite-popper" teleported style="width: 90px">
                <el-option v-for="o in maxUsesOptions" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </div>
            <el-button type="primary" size="small" :loading="generating" @click="generateTimedCode" class="timed-gen-btn">
              {{ generating ? '生成中...' : '生成' }}
            </el-button>
          </div>

          <!-- Timed code list -->
          <div v-if="timedCodes.length" class="timed-list">
            <div v-for="c in timedCodes" :key="c.id" class="timed-item" :class="{ 'timed-item--dead': isExpired(c) || isExhausted(c) || !c.is_active }">
              <div class="timed-code">{{ c.code }}</div>
              <div class="timed-meta">
                <span class="timed-status" :class="{ 'timed-status--dead': isExpired(c) || isExhausted(c) || !c.is_active }">{{ codeStatus(c) }}</span>
                <span class="timed-expires">{{ expiresFormat(c.expires_at) }}</span>
              </div>
              <div class="timed-item-actions">
                <el-button size="small" text @click="copyTimedCode(c.code)">复制</el-button>
                <el-button size="small" text type="danger" @click="deactivateTimedCode(c.id)">删除</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 48px;
  padding: 0 24px;
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-accent);
  cursor: pointer;
}

.stage-tag {
  font-size: 12px;
  color: var(--color-accent);
  background: rgba(43, 58, 103, 0.08);
  padding: 2px 10px;
  border-radius: 2px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.theme-btn {
  cursor: pointer;
  color: var(--color-text-secondary);
  transition: color 0.2s;
}
.theme-btn:hover {
  color: var(--color-accent);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.app-content {
  flex: 1;
}

.invite-link {
  font-size: 12px; color: var(--color-text-secondary);
  cursor: pointer; user-select: none;
  padding: 2px 8px; border-radius: 3px;
  transition: all 0.2s;
}
.invite-link:hover {
  color: var(--color-accent);
  background: rgba(43, 58, 103, 0.06);
}

/* invite dialog */
.invite-dialog-body { text-align: center; }
.invite-code-display {
  font-size: 28px; font-weight: 700; letter-spacing: 6px;
  color: var(--color-accent); margin-bottom: 8px;
  font-family: 'Courier New', monospace;
}
.invite-countdown {
  font-size: 13px; color: var(--color-text-secondary);
  display: flex; align-items: center; justify-content: center; gap: 6px;
  margin-bottom: 20px;
}
.countdown-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #67C23A; animation: blink 1.5s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
.invite-actions { display: flex; gap: 12px; justify-content: center; margin-bottom: 8px; }
.invite-tip { font-size: 12px; color: var(--color-text-secondary); margin: 0; }

.app-footer {
  text-align: center;
  padding: 10px 24px;
  font-size: 12px;
  color: var(--color-text-secondary);
  border-top: 1px solid var(--color-border-light);
  background: var(--color-card);
  flex-shrink: 0;
}

/* --- Bottom Tab Bar (mobile) --- */
.bottom-tabs {
  display: none;
}
.mobile-only {
  display: none;
}

@media (max-width: 768px) {
  .app-header {
    height: 40px;
    padding: 0 12px;
  }

  .header-right {
    gap: 8px;
  }

  .desktop-only {
    display: none !important;
  }
  .mobile-only {
    display: inline;
  }

  .app-footer {
    display: none;
  }

  .app-content {
    padding-bottom: 56px;
  }

  .invite-code-display {
    font-size: 22px;
    letter-spacing: 4px;
  }

  .bottom-tabs {
    display: flex;
    justify-content: space-around;
    align-items: center;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    background: var(--color-card);
    border-top: 1px solid var(--color-border);
    z-index: 1000;
    padding-bottom: env(safe-area-inset-bottom);
  }

  .tab-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 4px 12px;
    cursor: pointer;
    color: var(--color-text-secondary);
    transition: color 0.2s;
  }

  .tab-item.active {
    color: var(--color-accent);
  }

  .tab-label {
    font-size: 10px;
    line-height: 1;
  }
}

/* invite dialog — timed codes */
.invite-dialog :deep(.el-dialog__body) {
  padding: 16px 20px;
  overflow: visible;
}

.invite-section {
  text-align: center;
}
.invite-section-title {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* timed form */
.timed-form {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.timed-form-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.timed-form-item label {
  font-size: 12px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
.timed-gen-btn {
  flex-shrink: 0;
}

/* timed list */
.timed-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 40vh;
  overflow-y: auto;
}
.timed-item {
  background: var(--color-bg);
  border-radius: 8px;
  padding: 10px 12px;
  text-align: left;
}
.timed-item--dead {
  opacity: 0.45;
}
.timed-code {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 3px;
  color: var(--color-accent);
  font-family: 'Courier New', monospace;
  margin-bottom: 4px;
}
.timed-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.timed-status {
  font-size: 11px;
  color: #67C23A;
}
.timed-status--dead {
  color: var(--color-text-secondary);
}
.timed-expires {
  font-size: 11px;
  color: var(--color-text-secondary);
}
.timed-item-actions {
  display: flex;
  gap: 4px;
  justify-content: flex-end;
}

/* mobile dialog */
@media (max-width: 768px) {
  .invite-dialog {
    --el-dialog-width: 90vw !important;
    max-width: 380px;
  }
  .invite-dialog :deep(.el-dialog__body) {
    padding: 12px 14px;
  }
  .timed-code {
    font-size: 16px;
    letter-spacing: 2px;
  }
  .timed-form {
    gap: 6px;
  }
}
</style>

<style>
/* el-select popper teleported to body — dialog z-index is 2000+, dropdown must sit above it */
.invite-popper {
  z-index: 9999 !important;
}
</style>
