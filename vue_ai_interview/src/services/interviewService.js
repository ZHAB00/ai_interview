import api from './api.js'

export function createInterview(params) {
  return api.post('/api/interviews', params)
}

export function getInterviewHistory(page = 1, pageSize = 20) {
  return api.get('/api/interviews/history', { params: { page, page_size: pageSize } })
}

export function getInterviewReport(interviewId) {
  return api.get(`/api/interviews/${interviewId}/report`)
}

export function submitFeedback(reportId, feedback) {
  return api.post(`/api/reports/${reportId}/feedback`, feedback)
}
