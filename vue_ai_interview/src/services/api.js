import axios from 'axios'
import { useAuthStore } from '../stores/authStore.js'
import router from '../router/index.js'

export function getBaseURL() {
  const url = import.meta.env.VITE_API_BASE_URL
  if (url === undefined) {
    throw new Error(
      'VITE_API_BASE_URL is not configured. Please set it in your .env file ' +
      '(e.g. VITE_API_BASE_URL=http://localhost:8000)'
    )
  }
  return url
}

const api = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.accessToken) {
      config.headers.Authorization = `Bearer ${authStore.accessToken}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error)
    } else {
      resolve(token)
    }
  })
  failedQueue = []
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then(() => {
            const authStore = useAuthStore()
            originalRequest.headers.Authorization = `Bearer ${authStore.accessToken}`
            return api(originalRequest)
          })
      }

      originalRequest._retry = true
      isRefreshing = true

      const authStore = useAuthStore()
      try {
        const success = await authStore.refreshAccessToken()
        if (success) {
          processQueue(null, authStore.accessToken)
          originalRequest.headers.Authorization = `Bearer ${authStore.accessToken}`
          return api(originalRequest)
        }
        processQueue(new Error('Refresh failed'))
        router.push('/login')
        return Promise.reject(error)
      } catch (err) {
        processQueue(err)
        authStore.logout()
        router.push('/login')
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default api
