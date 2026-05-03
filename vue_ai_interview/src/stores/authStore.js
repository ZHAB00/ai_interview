import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import api, { getBaseURL } from '../services/api.js'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const userInfo = ref(JSON.parse(localStorage.getItem('user_info') || 'null'))

  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => userInfo.value?.role === 'admin')
  const username = computed(() => userInfo.value?.username || '')

  function saveTokens(access, refresh) {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem('access_token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function saveUserInfo(info) {
    userInfo.value = info
    localStorage.setItem('user_info', JSON.stringify(info))
  }

  async function login(phone, password) {
    const { data } = await api.post('/api/auth/login', { phone, password })
    saveTokens(data.access_token, data.refresh_token)
    saveUserInfo({ user_id: data.user_id, username: data.username, role: data.role })
    return data
  }

  async function register(phone, username, password, inviteCode, smsToken) {
    const { data } = await api.post('/api/auth/register', { phone, username, password, invite_code: inviteCode, sms_token: smsToken })
    return data
  }

  async function refreshAccessToken() {
    if (!refreshToken.value) return false
    try {
      const baseURL = getBaseURL()
      const { data } = await axios.post(`${baseURL}/api/auth/refresh`, {
        refresh_token: refreshToken.value
      })
      saveTokens(data.access_token, data.refresh_token)
      saveUserInfo({ user_id: data.user_id, username: data.username, role: data.role })
      return true
    } catch {
      return false
    }
  }

  function logout() {
    accessToken.value = ''
    refreshToken.value = ''
    userInfo.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
  }

  return {
    accessToken, refreshToken, userInfo,
    isLoggedIn, isAdmin, username,
    login, register, refreshAccessToken, logout, saveUserInfo
  }
})
