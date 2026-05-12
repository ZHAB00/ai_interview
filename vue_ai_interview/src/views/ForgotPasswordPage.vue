<script setup>
import { reactive, ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { sendSms, verifySms, resetPassword } from '../services/authService.js'

const router = useRouter()

const step = ref(1)
const loading = ref(false)
const errorMsg = ref('')
const smsCountdown = ref(0)
let countdownTimer = null

const form = reactive({
  phone: '',
  smsCode: '',
  newPassword: '',
  confirmPassword: ''
})

async function handleSendSms() {
  if (form.phone.length !== 11) {
    errorMsg.value = '请输入正确的11位手机号'
    return
  }
  loading.value = true; errorMsg.value = ''
  try {
    await sendSms(form.phone, 'reset_password')
    smsCountdown.value = 60
    countdownTimer = setInterval(() => { smsCountdown.value--; if (smsCountdown.value <= 0) clearInterval(countdownTimer) }, 1000)
    step.value = 2
    ElMessage.success('验证码已发送')
  } catch (err) {
    errorMsg.value = err.response?.data?.error?.message || '发送失败'
  } finally { loading.value = false }
}

async function handleReset() {
  if (!form.smsCode || form.smsCode.length < 4) { errorMsg.value = '请输入验证码'; return }
  if (form.newPassword.length < 8) { errorMsg.value = '密码至少8位'; return }
  if (!/[a-zA-Z]/.test(form.newPassword)) { errorMsg.value = '密码必须包含英文字母'; return }
  if (!/\d/.test(form.newPassword)) { errorMsg.value = '密码必须包含数字'; return }
  if (form.newPassword !== form.confirmPassword) { errorMsg.value = '两次密码不一致'; return }

  loading.value = true; errorMsg.value = ''
  try {
    const vRes = await verifySms(form.phone, form.smsCode, 'reset_password')
    if (!vRes.data.success) { errorMsg.value = vRes.data.message || '验证码错误'; loading.value = false; return }
    await resetPassword(form.phone, vRes.data.token, form.newPassword)
    ElMessage.success('密码重置成功，请登录')
    router.push('/login')
  } catch (err) {
    errorMsg.value = err.response?.data?.error?.message || '重置失败'
  } finally { loading.value = false }
}

onUnmounted(() => clearInterval(countdownTimer))
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2 class="auth-title">忘记密码</h2>
      <p class="auth-subtitle">通过手机短信验证码重置密码</p>

      <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon closable @close="errorMsg = ''" style="margin-bottom: 16px" />

      <!-- Step 1: Phone -->
      <div v-if="step === 1">
        <el-input v-model="form.phone" placeholder="请输入注册手机号" size="large" maxlength="11" style="margin-bottom: 12px" />
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleSendSms">
          发送验证码
        </el-button>
      </div>

      <!-- Step 2: SMS + new password -->
      <div v-if="step === 2">
        <div style="display: flex; gap: 8px; margin-bottom: 12px">
          <el-input v-model="form.smsCode" placeholder="验证码" size="large" maxlength="6" style="flex: 1" />
          <el-button size="large" :disabled="smsCountdown > 0" @click="handleSendSms">
            {{ smsCountdown > 0 ? smsCountdown + 's' : '重发' }}
          </el-button>
        </div>
        <el-input v-model="form.newPassword" type="password" placeholder="新密码（至少8位，含英文和数字）" size="large" show-password style="margin-bottom: 12px" />
        <el-input v-model="form.confirmPassword" type="password" placeholder="确认新密码" size="large" show-password style="margin-bottom: 12px" />
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleReset">
          重置密码
        </el-button>
      </div>

      <p class="auth-switch">
        <router-link to="/login">返回登录</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page { display: flex; justify-content: center; align-items: center; min-height: calc(100vh - 48px - 38px); padding: 40px 20px; }
.auth-card { width: 400px; padding: 40px; background: var(--color-card); border: 1px solid var(--color-border); border-radius: 4px; }
.auth-title { font-size: 22px; font-weight: 600; color: var(--color-text); margin-bottom: 4px; }
.auth-subtitle { font-size: 13px; color: var(--color-text-secondary); margin-bottom: 24px; }
.auth-switch { text-align: center; font-size: 13px; color: var(--color-text-secondary); margin-top: 20px; }
.auth-switch a { color: var(--color-accent); text-decoration: none; }

@media (max-width: 768px) {
  .auth-page { padding: 24px 16px; align-items: flex-start; padding-top: 40px; }
  .auth-card { width: 100%; padding: 24px 20px; }
}
</style>
