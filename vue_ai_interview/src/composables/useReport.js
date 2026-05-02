import { ref, onUnmounted } from 'vue'
import { getInterviewReport, submitFeedback as submitFeedbackApi } from '../services/interviewService.js'
import { REPORT_POLL_INTERVAL } from '../utils/constants.js'

export function useReport(interviewId) {
  const loading = ref(true)
  const report = ref(null)
  const error = ref('')
  let pollTimer = null
  let destroyed = false

  async function fetchReport() {
    try {
      const { data } = await getInterviewReport(interviewId)

      if (data.status === 'generating') {
        // Keep polling
        if (!destroyed) {
          pollTimer = setTimeout(fetchReport, REPORT_POLL_INTERVAL)
        }
        return
      }

      if (data.status === 'completed') {
        report.value = data.report
        loading.value = false
        return
      }

      // status === 'error'
      error.value = '报告生成失败'
      loading.value = false
    } catch (err) {
      if (err.response?.status === 404) {
        error.value = '面试记录不存在'
      } else {
        error.value = '获取报告失败，请稍后重试'
      }
      loading.value = false
    }
  }

  function startPolling() {
    loading.value = true
    error.value = ''
    report.value = null
    destroyed = false
    fetchReport()
  }

  async function submitFeedback(feedback) {
    try {
      await submitFeedbackApi(interviewId, feedback)
      return true
    } catch {
      return false
    }
  }

  function stop() {
    destroyed = true
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  onUnmounted(stop)

  return { loading, report, error, startPolling, submitFeedback, stop }
}
