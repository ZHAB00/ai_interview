<script setup>
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { checkInviteCode, sendSms, verifySms } from '../services/authService.js'
import { useAuthStore } from '../stores/authStore.js'

const router = useRouter()
const authStore = useAuthStore()

// Step control: 1=invite_code, 2=sms, 3=password
const step = ref(1)
const loading = ref(false)
const errorMsg = ref('')
const smsSent = ref(false)
const smsCountdown = ref(0)
let countdownTimer = null

const form = reactive({
  inviteCode: '',
  phone: '',
  smsCode: '',
  username: '',
  password: '',
  confirmPassword: ''
})

// ── Step 1: Verify invite code ──
async function checkInviteCodeHandler() {
  const code = form.inviteCode.trim()
  if (code.length < 4) {
    errorMsg.value = '邀请码长度不足'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await checkInviteCode(code)
    step.value = 2
  } catch (err) {
    const msg = err.response?.data?.error?.message || '邀请码无效'
    errorMsg.value = msg
  } finally {
    loading.value = false
  }
}

// ── Step 2: Send SMS ──
async function handleSendSms() {
  if (smsCountdown.value > 0) return
  if (form.phone.length !== 11) {
    errorMsg.value = '请输入正确的11位手机号'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await sendSms(form.phone, 'register')
    smsSent.value = true
    smsCountdown.value = 60
    countdownTimer = setInterval(() => {
      smsCountdown.value--
      if (smsCountdown.value <= 0) {
        clearInterval(countdownTimer)
      }
    }, 1000)
    ElMessage.success('验证码已发送')
  } catch (err) {
    const msg = err.response?.data?.error?.message || '发送失败'
    if (msg.includes('已注册')) {
      errorMsg.value = '该手机号已注册'
    } else {
      errorMsg.value = msg
    }
  } finally {
    loading.value = false
  }
}

// ── Step 3: Verify SMS + Register ──
async function handleRegister() {
  if (!form.smsCode || form.smsCode.length < 4) {
    errorMsg.value = '请输入短信验证码'
    return
  }
  if (form.password.length < 8) {
    errorMsg.value = '密码至少8位，需含英文和数字'
    return
  }
  if (!/[a-zA-Z]/.test(form.password)) {
    errorMsg.value = '密码必须包含英文字母'
    return
  }
  if (!/\d/.test(form.password)) {
    errorMsg.value = '密码必须包含数字'
    return
  }
  if (form.password !== form.confirmPassword) {
    errorMsg.value = '两次密码不一致'
    return
  }

  loading.value = true
  errorMsg.value = ''
  try {
    // Step 3a: Verify SMS → get temp token
    const verifyRes = await verifySms(form.phone, form.smsCode, 'register')
    if (!verifyRes.data.success) {
      errorMsg.value = verifyRes.data.message || '验证码错误'
      loading.value = false
      return
    }
    const smsToken = verifyRes.data.token

    // Step 3b: Register
    await authStore.register(form.phone, form.username, form.password, form.inviteCode, smsToken)
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (err) {
    const msg = err.response?.data?.error?.message || ''
    if (err.response?.status === 409) {
      errorMsg.value = '该手机号已注册'
    } else if (msg.includes('邀请码')) {
      errorMsg.value = '邀请码不正确'
    } else if (msg.includes('短信') || msg.includes('验证')) {
      errorMsg.value = '短信验证未通过'
    } else if (msg.includes('密码')) {
      errorMsg.value = msg
    } else {
      errorMsg.value = msg || '注册失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

// Cleanup
import { onUnmounted } from 'vue'
onUnmounted(() => clearInterval(countdownTimer))
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2 class="auth-title">注册</h2>
      <p class="auth-subtitle">三步安全注册</p>

      <!-- Steps indicator -->
      <div class="step-bar">
        <div class="step-item" :class="{ active: step >= 1, done: step > 1 }">
          <span class="step-num">1</span> 邀请码
        </div>
        <div class="step-line" :class="{ done: step > 1 }" />
        <div class="step-item" :class="{ active: step >= 2, done: step > 2 }">
          <span class="step-num">2</span> 手机验证
        </div>
        <div class="step-line" :class="{ done: step > 2 }" />
        <div class="step-item" :class="{ active: step >= 3 }">
          <span class="step-num">3</span> 设置密码
        </div>
      </div>

      <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon closable @close="errorMsg = ''" style="margin-bottom: 16px" />

      <!-- Step 1: Invite code -->
      <div v-if="step === 1">
        <el-input
          v-model="form.inviteCode"
          placeholder="请输入内测邀请码"
          size="large"
          maxlength="32"
          @keyup.enter="checkInviteCodeHandler"
        />
        <el-button type="primary" size="large" style="width: 100%; margin-top: 16px" :loading="loading" @click="checkInviteCodeHandler">
          下一步
        </el-button>
      </div>

      <!-- Step 2: Phone + SMS -->
      <div v-if="step === 2">
        <el-input v-model="form.phone" placeholder="请输入手机号" size="large" maxlength="11" style="margin-bottom: 12px" />
        <div style="display: flex; gap: 8px">
          <el-input v-model="form.smsCode" placeholder="短信验证码" size="large" maxlength="6" style="flex: 1" />
          <el-button size="large" :disabled="smsCountdown > 0" :loading="loading" @click="handleSendSms">
            {{ smsCountdown > 0 ? smsCountdown + 's' : smsSent ? '重新发送' : '发送验证码' }}
          </el-button>
        </div>
        <el-button type="primary" size="large" style="width: 100%; margin-top: 16px" @click="step = 3" :disabled="!smsSent">
          下一步
        </el-button>
      </div>

      <!-- Step 3: Password + Register -->
      <div v-if="step === 3">
        <el-input v-model="form.username" placeholder="用户名（2-30个字符）" size="large" maxlength="30" style="margin-bottom: 12px" />
        <el-input v-model="form.password" type="password" placeholder="密码（至少8位，含英文和数字）" size="large" show-password style="margin-bottom: 12px" />
        <el-input v-model="form.confirmPassword" type="password" placeholder="确认密码" size="large" show-password style="margin-bottom: 12px" />
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleRegister">
          注册
        </el-button>
      </div>

      <p class="auth-switch">
        已有账号？<router-link to="/login">去登录</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex; justify-content: center; align-items: center;
  min-height: calc(100vh - 48px - 38px); padding: 40px 20px;
}
.auth-card { width: 420px; padding: 40px; background: var(--color-card); border: 1px solid var(--color-border); border-radius: 4px; }
.auth-title { font-size: 22px; font-weight: 600; color: var(--color-text); margin-bottom: 4px; }
.auth-subtitle { font-size: 13px; color: var(--color-text-secondary); margin-bottom: 24px; }
.auth-switch { text-align: center; font-size: 13px; color: var(--color-text-secondary); margin-top: 20px; }
.auth-switch a { color: var(--color-accent); text-decoration: none; }

.step-bar { display: flex; align-items: center; justify-content: center; margin-bottom: 20px; gap: 0; }
.step-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-text-secondary); }
.step-item.active { color: var(--color-accent); font-weight: 600; }
.step-item.done { color: #67C23A; }
.step-num {
  width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--color-text-secondary);
  display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 600;
}
.step-item.active .step-num { border-color: var(--color-accent); background: var(--color-accent); color: #fff; }
.step-item.done .step-num { border-color: #67C23A; background: #67C23A; color: #fff; }
.step-line { width: 32px; height: 2px; background: var(--color-border); margin: 0 4px; }
.step-line.done { background: #67C23A; }

@media (max-width: 768px) {
  .auth-page { padding: 24px 16px; align-items: flex-start; padding-top: 40px; }
  .auth-card { width: 100%; padding: 24px 20px; }
}
</style>
