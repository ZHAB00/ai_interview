import api from './api.js'

// Questions CRUD
export function getQuestions(params) {
  return api.get('/api/admin/questions', { params })
}

export function createQuestion(data) {
  return api.post('/api/admin/questions', data)
}

export function updateQuestion(id, data) {
  return api.put(`/api/admin/questions/${id}`, data)
}

export function deleteQuestion(id) {
  return api.delete(`/api/admin/questions/${id}`)
}

// Document management
export function uploadDocument(formData) {
  return api.post('/api/admin/documents', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function getDocuments(params) {
  return api.get('/api/admin/documents', { params })
}

export function getDocumentStatus(id) {
  return api.get(`/api/admin/documents/${id}`)
}

export function deleteDocument(id) {
  return api.delete(`/api/admin/documents/${id}`)
}

export function reprocessDocument(id) {
  return api.post(`/api/admin/documents/${id}/reprocess`)
}
