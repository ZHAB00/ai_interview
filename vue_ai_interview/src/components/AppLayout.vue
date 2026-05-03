<script setup>
import { computed, ref, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/authStore.js'
import { useInterviewStore } from '../stores/interviewStore.js'
import NetworkStatus from './NetworkStatus.vue'
import { ETHICS_STATEMENT } from '../utils/constants.js'
import api from '../services/api.js'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const interviewStore = useInterviewStore()

const isInterviewActive = computed(() =>
  interviewStore.status === 'in_progress'
)

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
  if (diffMin >= 15) diffMin -= 15 // wrap: should not happen, defensive
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
</style>
