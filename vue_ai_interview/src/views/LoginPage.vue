<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore.js'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({
  phone: '',
  password: ''
})
const loading = ref(false)
const errorMsg = ref('')

const rules = {
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '手机号格式不正确', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ]
}

const formRef = ref(null)

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  errorMsg.value = ''
  try {
    await authStore.login(form.phone, form.password)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (err) {
    errorMsg.value = err.response?.data?.error?.message || '登录失败，请检查手机号或密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h2 class="auth-title">登录</h2>
      <p class="auth-subtitle">AI面试官 — 模拟面试练习平台</p>

      <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon closable @close="errorMsg = ''" style="margin-bottom: 16px" />

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="请输入手机号" maxlength="11" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" native-type="submit" style="width: 100%">
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <p class="auth-switch">
        还没有账号？<router-link to="/register">立即注册</router-link>
        <span style="margin: 0 8px">|</span>
        <router-link to="/forgot-password">忘记密码</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 48px - 38px);
  padding: 40px 20px;
}

.auth-card {
  width: 400px;
  padding: 40px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px;
}

.auth-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 4px;
}

.auth-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
}

.auth-switch {
  text-align: center;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.auth-switch a {
  color: var(--color-accent);
  text-decoration: none;
}
</style>
