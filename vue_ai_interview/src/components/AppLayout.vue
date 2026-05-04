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
    { key: 'dashboard', label: '首页', icon: 'HomeFilled', path: '/dashboard' },
    { key: 'interview', label: '面试', icon: 'Mic', path: isInterviewActive.value ? route.path : '/dashboard' },
    { key: 'report', label: '报告', icon: 'Document', path: '/dashboard' },
  ]
  if (authStore.isAdmin) {
    items.push({ key: 'admin', label: '管理', icon: 'Setting', path: adminTabSub.value === 'questions' ? '/admin/questions' : '/admin/documents' })
  }
  return items
})

const activeTab = computed(() => {
  const p = route.path
  if (p.startsWith('/interview')) return 'interview'
  if (p.startsWith('/report')) return 'report'
  if (p.startsWith('/admin')) return 'admin'
  return 'dashboard'
})

function goTab(tab) {
  // Interview tab while in interview: stay there
  if (tab.key === 'interview' && isInterviewActive.value) return

  // Leaving interview: confirm
  if (isInterviewActive.value && (tab.key === 'dashboard' || tab.key === 'report' || tab.key === 'admin')) {
    ElMessageBox.confirm('正在面试中，确定离开吗？', '提示', { confirmButtonText: '离开', cancelButtonText: '继续面试', type: 'warning' })
      .then(() => router.push(tab.path))
      .catch(() => {})
    return
  }

  // Interview tab without active interview
  if (tab.key === 'interview' && !isInterviewActive.value) {
    if (hasActiveInterview.value) {
      router.push(`/interview/${activeInterviewId.value}`)
      return
    }
    ElMessage.info('暂无进行中的面试，请先上传简历创建面试')
    return
  }

  // Report tab
  if (tab.key === 'report') {
    router.push(tab.path)
    return
  }

  router.push(tab.path)
}

// --- Invite Code ---
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
        <span v-if="authStore.isAdmin" class="invite-link" @click="openInviteDialog">邀请码</span>
        <el-dropdown trigger="click" v-if="authStore.isLoggedIn">
          <span class="user-info">
            {{ authStore.username || '用户' }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push('/dashboard')">首页</el-dropdown-item>
              <el-dropdown-item v-if="authStore.isAdmin" @click="router.push('/admin/questions')">题库管理</el-dropdown-item>
              <el-dropdown-item v-if="authStore.isAdmin" @click="router.push('/admin/documents')">文档管理</el-dropdown-item>
              <el-dropdown-item divided disabled>主题：{{ themeLabel }}</el-dropdown-item>
              <el-dropdown-item @click="setTheme('light')" :class="{ 'theme-active': currentTheme === 'light' }">☀️ 浅色</el-dropdown-item>
              <el-dropdown-item @click="setTheme('dark')" :class="{ 'theme-active': currentTheme === 'dark' }">🌙 深色</el-dropdown-item>
              <el-dropdown-item @click="setTheme('warm')" :class="{ 'theme-active': currentTheme === 'warm' }">🔥 暖色</el-dropdown-item>
              <el-dropdown-item divided @click="handleLogout">退出登录</el-dropdown-item>
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

    <!-- Bottom Tab Bar (mobile only, hidden during interview) -->
    <nav v-if="!isInterviewActive" class="bottom-tabs">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeTab === tab.key }"
        @click="goTab(tab)"
      >
        <el-icon :size="20"><component :is="tab.icon" /></el-icon>
        <span class="tab-label">{{ tab.label }}</span>
      </div>
    </nav>

    <!-- Invite Code Dialog -->
    <el-dialog v-model="inviteDialog" title="内测邀请码" width="380px" :close-on-click-modal="false" @close="closeInviteDialog">
      <div class="invite-dialog-body">
        <div class="invite-code-display">{{ inviteCode }}</div>
        <div class="invite-countdown">
          <span class="countdown-dot" />
          {{ countdown }}
        </div>
        <div class="invite-actions">
          <el-button type="primary" @click="copyInviteCode">复制邀请码</el-button>
          <el-button text @click="fetchInviteCode">立即刷新</el-button>
        </div>
        <p class="invite-tip">同一窗口内上一个码也有效（15分钟容错）</p>
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

@media (max-width: 768px) {
  .app-header {
    height: 40px;
    padding: 0 12px;
  }

  .header-right {
    gap: 8px;
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
</style>
