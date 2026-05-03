import api from './api.js'

export function login(phone, password) {
  return api.post('/api/auth/login', { phone, password })
}

export function register(phone, username, password, inviteCode, smsToken) {
  return api.post('/api/auth/register', { phone, username, password, invite_code: inviteCode, sms_token: smsToken })
}

export function refreshToken(refreshTokenVal) {
  return api.post('/api/auth/refresh', { refresh_token: refreshTokenVal })
}

export function sendSms(phone, captchaType = 'register') {
  return api.post('/api/captcha/send', { phone, captcha_type: captchaType })
}

export function verifySms(phone, code, captchaType = 'register') {
  return api.post('/api/captcha/verify', { phone, code, captcha_type: captchaType })
}

export function resetPassword(phone, smsToken, newPassword) {
  return api.post('/api/auth/reset-password', { phone, sms_token: smsToken, new_password: newPassword })
}

// Logout is handled locally (clear tokens + redirect), no server endpoint needed
