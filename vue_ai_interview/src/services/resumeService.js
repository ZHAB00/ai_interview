import api from './api.js'

export function uploadResume(formData, onProgress) {
  return api.post('/api/resumes/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
    onUploadProgress: (event) => {
      if (onProgress) {
        const percent = Math.round((event.loaded / event.total) * 100)
        onProgress(percent)
      }
    }
  })
}

export function getResumeDetail(resumeId) {
  return api.get(`/api/resumes/${resumeId}`)
}
