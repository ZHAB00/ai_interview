<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/authStore.js'
import api from '../services/api.js'

const authStore = useAuthStore()
const open = ref(false)
const messages = ref([])
const text = ref('')
const sending = ref(false)
const listRef = ref(null)
const pressingId = ref(null)
let longPressTimer = null

async function loadMessages() {
  try {
    const { data } = await api.get('/api/messages')
    messages.value = data.items || []
  } catch { messages.value = [] }
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

function toggle() {
  open.value = !open.value
  if (open.value) loadMessages()
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="msg-board" :class="{ open }">
    <!-- Floating button -->
    <button class="msg-fab" @click="toggle" v-if="!open">
      <span>💬</span>
    </button>

    <!-- Panel -->
    <div class="msg-panel" v-if="open">
      <div class="msg-header">
        <span>留言板</span>
        <button class="msg-close" @click="open = false">✕</button>
      </div>

      <div class="msg-list" ref="listRef" v-if="messages.length">
        <div v-for="m in messages" :key="m.id" class="msg-item"
          :class="{ 'msg-item--pressing': pressingId === m.id }"
          @touchstart="startPress(m)" @touchend="cancelPress" @touchmove="cancelPress"
          @mousedown="startPress(m)" @mouseup="cancelPress" @mouseleave="cancelPress">
          <div class="msg-meta">
            <span class="msg-user">
              <span class="msg-admin-tag" v-if="m.role === 'admin'">管理员</span>
              {{ m.username }}
            </span>
            <span class="msg-time">{{ fmtTime(m.created_at) }}</span>
          </div>
          <div class="msg-text">{{ m.content }}</div>
        </div>
      </div>
      <div class="msg-empty" v-else>暂无留言，来说两句吧</div>

      <div class="msg-input" v-if="authStore.isLoggedIn">
        <input
          v-model="text"
          placeholder="说点什么...（限100字，每天3条）"
          maxlength="100"
          @keyup.enter="sendMessage"
        />
        <button :disabled="!text.trim() || sending" @click="sendMessage">
          {{ sending ? '发送中' : '发送' }}
        </button>
      </div>
      <div class="msg-login-hint" v-else>
        <router-link to="/login" @click="open = false">登录</router-link>后参与讨论
      </div>
    </div>
  </div>
</template>

<style scoped>
.msg-board { position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); z-index: 900; }
.msg-board.open { bottom: 0; left: 0; right: 0; transform: none; }

/* FAB */
.msg-fab {
  width: 48px; height: 48px; border-radius: 50%;
  background: var(--color-accent); color: #fff; border: none;
  font-size: 22px; cursor: pointer; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.2s;
}
.msg-fab:hover { transform: scale(1.1); }

/* Panel */
.msg-panel {
  width: 100vw; max-width: 480px; margin: 0 auto;
  height: 50vh; background: var(--color-card);
  border-top: 1px solid var(--color-border);
  border-radius: 12px 12px 0 0;
  display: flex; flex-direction: column;
  box-shadow: 0 -4px 20px rgba(0,0,0,0.1);
}
.msg-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--color-border);
  font-size: 15px; font-weight: 600;
}
.msg-close { background: none; border: none; font-size: 18px; cursor: pointer; color: var(--color-text-secondary); }

.msg-list { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.msg-item { padding-bottom: 10px; border-bottom: 1px solid var(--color-border-light); }
.msg-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.msg-user { font-size: 13px; font-weight: 500; color: var(--color-accent); }
.msg-admin-tag {
  display: inline-block; font-size: 10px; background: var(--color-accent); color: #fff;
  padding: 1px 5px; border-radius: 3px; margin-right: 4px; vertical-align: middle; line-height: 1.4;
}
.msg-item--pressing { opacity: 0.6; transition: opacity 0.15s; }
.msg-time { font-size: 11px; color: var(--color-text-secondary); }
.msg-text { font-size: 14px; color: var(--color-text); line-height: 1.5; }
.msg-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--color-text-secondary); font-size: 14px; }

.msg-input { display: flex; gap: 8px; padding: 10px 16px; border-top: 1px solid var(--color-border); }
.msg-input input { flex: 1; padding: 8px 12px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 14px; outline: none; background: var(--color-bg); color: var(--color-text); }
.msg-input button { padding: 8px 16px; background: var(--color-accent); color: #fff; border: none; border-radius: 4px; cursor: pointer; white-space: nowrap; }
.msg-input button:disabled { opacity: 0.5; cursor: not-allowed; }
.msg-login-hint { padding: 12px 16px; text-align: center; font-size: 13px; color: var(--color-text-secondary); border-top: 1px solid var(--color-border); }
.msg-login-hint a { color: var(--color-accent); }

@media (max-width: 768px) {
  .msg-board:not(.open) { bottom: 100px; }
  .msg-panel { max-width: 100%; height: 55vh; }
}
</style>
