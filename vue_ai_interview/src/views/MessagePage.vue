<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/authStore.js'
import api from '../services/api.js'

const router = useRouter()
const authStore = useAuthStore()
const messages = ref([])
const text = ref('')
const sending = ref(false)
const listRef = ref(null)
const loading = ref(false)
const pressingId = ref(null)
let longPressTimer = null

async function loadMessages() {
  loading.value = true
  try {
    const { data } = await api.get('/api/messages')
    messages.value = data.items || []
  } catch { messages.value = [] }
  finally { loading.value = false }
}

async function sendMessage() {
  const t = text.value.trim()
  if (!t) return
  sending.value = true
  try {
    await api.post('/api/messages', { content: t })
    text.value = ''
    await loadMessages()
    await nextTick()
    if (listRef.value) listRef.value.scrollTop = 0
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '发送失败')
  } finally {
    sending.value = false
  }
}

async function deleteMessage(id) {
  try {
    await api.delete(`/api/messages/${id}`)
    await loadMessages()
  } catch (e) {
    ElMessage.error(e.response?.data?.error?.message || '删除失败')
  }
}

function canDelete(m) {
  return authStore.isAdmin || m.user_id === authStore.userInfo?.user_id
}

async function confirmDelete(m) {
  try {
    await ElMessageBox.confirm('确定删除这条留言？', '提示', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    await deleteMessage(m.id)
  } catch {}
}

function startPress(m) {
  if (!canDelete(m)) return
  pressingId.value = m.id
  longPressTimer = setTimeout(() => {
    pressingId.value = null
    confirmDelete(m)
  }, 600)
}

function cancelPress() {
  clearTimeout(longPressTimer)
  longPressTimer = null
  pressingId.value = null
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const m = d.getMonth() + 1
  const day = d.getDate()
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${m}-${day} ${h}:${min}`
}

onMounted(loadMessages)
</script>

<template>
  <div class="message-page">
    <header class="mp-header">
      <span class="mp-back" @click="router.back()">← 返回</span>
      <h2 class="mp-title">留言板</h2>
      <span class="mp-count">{{ messages.length }} 条</span>
    </header>

    <div class="mp-list" ref="listRef" v-loading="loading">
      <div class="mp-empty" v-if="!loading && !messages.length">
        <div class="mp-empty-icon">💬</div>
        <p>还没有留言</p>
        <p class="mp-empty-hint">来说两句吧</p>
      </div>

      <div v-for="m in messages" :key="m.id" class="mp-item"
        :class="{ 'mp-item--pressing': pressingId === m.id }"
        @touchstart.passive="startPress(m)" @touchend="cancelPress" @touchmove.passive="cancelPress"
        @mousedown="startPress(m)" @mouseup="cancelPress" @mouseleave="cancelPress">
        <div class="mp-avatar">{{ m.username.charAt(0) }}</div>
        <div class="mp-body">
          <div class="mp-meta">
            <span class="mp-user">
              <span class="mp-admin-tag" v-if="m.role === 'admin'">管理员</span>
              {{ m.username }}
            </span>
            <span class="mp-time">{{ fmtTime(m.created_at) }}</span>
          </div>
          <div class="mp-text">{{ m.content }}</div>
        </div>
      </div>
    </div>

    <div class="mp-input" v-if="authStore.isLoggedIn">
      <input
        v-model="text"
        placeholder="说点什么... 限100字，每天3条"
        maxlength="100"
        @keyup.enter="sendMessage"
      />
      <span class="mp-chars">{{ text.length }}/100</span>
      <button :disabled="!text.trim() || sending" @click="sendMessage">
        {{ sending ? '...' : '发送' }}
      </button>
    </div>
    <div class="mp-login-bar" v-else>
      <router-link to="/login">登录</router-link> 后参与留言
    </div>
  </div>
</template>

<style scoped>
.message-page {
  display: flex; flex-direction: column;
  height: calc(100vh - 48px);
  background: var(--color-bg);
}

/* Header */
.mp-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 16px; height: 48px; flex-shrink: 0;
  background: var(--color-card); border-bottom: 1px solid var(--color-border);
}
.mp-back { font-size: 14px; color: var(--color-accent); cursor: pointer; }
.mp-title { font-size: 16px; font-weight: 600; }
.mp-count { font-size: 12px; color: var(--color-text-secondary); }

/* List */
.mp-list {
  flex: 1; overflow-y: auto; padding: 12px 16px;
  display: flex; flex-direction: column; gap: 0;
}
.mp-empty { text-align: center; padding: 80px 0; color: var(--color-text-secondary); }
.mp-empty-icon { font-size: 48px; margin-bottom: 12px; }
.mp-empty-hint { font-size: 13px; margin-top: 4px; }

.mp-item {
  display: flex; gap: 10px; padding: 14px 0;
  border-bottom: 1px solid var(--color-border-light);
}
.mp-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--color-accent); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600; flex-shrink: 0;
}
.mp-body { flex: 1; min-width: 0; }
.mp-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.mp-user { font-size: 14px; font-weight: 500; color: var(--color-accent); }
.mp-admin-tag {
  display: inline-block; font-size: 10px; background: var(--color-accent); color: #fff;
  padding: 1px 5px; border-radius: 3px; margin-right: 4px; vertical-align: middle; line-height: 1.4;
}
.mp-item--pressing { opacity: 0.6; transition: opacity 0.15s; }
.mp-time { font-size: 11px; color: var(--color-text-secondary); }
.mp-text { font-size: 15px; color: var(--color-text); line-height: 1.6; word-break: break-word; }

/* Input */
.mp-input {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; flex-shrink: 0;
  background: var(--color-card); border-top: 1px solid var(--color-border);
}
.mp-input input {
  flex: 1; padding: 10px 12px; border: 1px solid var(--color-border);
  border-radius: 20px; font-size: 14px; outline: none;
  background: var(--color-bg); color: var(--color-text);
}
.mp-chars { font-size: 11px; color: var(--color-text-secondary); }
.mp-input button {
  padding: 10px 20px; background: var(--color-accent); color: #fff;
  border: none; border-radius: 20px; cursor: pointer; font-size: 14px;
}
.mp-input button:disabled { opacity: 0.5; cursor: not-allowed; }
.mp-login-bar { text-align: center; padding: 12px; font-size: 13px; color: var(--color-text-secondary); background: var(--color-card); border-top: 1px solid var(--color-border); }
.mp-login-bar a { color: var(--color-accent); }

/* Mobile */
@media (max-width: 768px) {
  .message-page { height: calc(100vh - 40px - 56px); }
  .mp-header { padding: 0 12px; height: 44px; }
  .mp-title { font-size: 15px; }
}
</style>
