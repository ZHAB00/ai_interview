import api from './api.js'

export function createInterview(params) {
  return api.post('/api/interviews', params)
}

export function getInterviewHistory(page = 1, pageSize = 8) {
  return api.get('/api/interviews/history', { params: { page, page_size: pageSize } })
}

export function getInterviewReport(interviewId) {
  return api.get(`/api/interviews/${interviewId}/report`)
}

export function getActiveInterview() {
  return api.get('/api/interviews/active')
}

export function reconnectInterview(interviewId) {
  return api.post(`/api/interviews/${interviewId}/reconnect`)
}

export function toggleFavorite(interviewId) {
  return api.put(`/api/interviews/${interviewId}/favorite`)
}

export function deleteInterview(interviewId) {
  return api.delete(`/api/interviews/${interviewId}`)
}

export function submitFeedback(interviewId, feedback) {
  return api.post(`/api/feedback/${interviewId}`, feedback)
}
