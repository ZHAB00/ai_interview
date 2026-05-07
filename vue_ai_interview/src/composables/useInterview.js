import { ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useInterviewStore } from '../stores/interviewStore.js'
import { storeToRefs } from 'pinia'
import { useWebSocket } from './useWebSocket.js'
import { useAudioRecorder } from './useAudioRecorder.js'
import { AI_STATUS, INTERVIEW_STATUS } from '../utils/constants.js'
import { pcm16ToWav } from '../utils/audioUtils.js'
import { ElMessage } from 'element-plus'

/**
 * Orchestrates interview session: WebSocket + PTT AudioRecorder + AudioPlayback.
 * Mic is manual push-to-talk: user clicks to start, clicks to stop.
 * STT result appears as editable draft bubble before sending.
 */
export function useInterview(options = {}) {
  const { externalVAD = null } = options

  const router = useRouter()
  const store = useInterviewStore()

  // --- AI Audio Playback ---
  // Uses a single persistent <audio> element, pre-unlocked during user gesture.
  let audioQueue = []
  let audioEl = null
  let activePlay = null  // tracks the current play cycle (not the element)

  function getAudioElement() {
    if (!audioEl) {
      audioEl = new Audio()
      audioEl.preload = 'auto'
    }
    return audioEl
  }

  function unlockAudio() {
    // Play a silent WAV during user gesture to satisfy browser autoplay policy.
    // This "unlocks" the element for all future programmatic plays.
    const silentWav = pcm16ToWav(new Uint8Array(160), 24000) // ~3ms silence, unlock audio
    const blob = new Blob([silentWav], { type: 'audio/wav' })
    const url = URL.createObjectURL(blob)
    const el = getAudioElement()
    el.src = url
    el.load()
    el.play().then(() => {
      console.log('[音频播放] 音频已解锁，后续TTS语音可以正常播放')
    }).catch(e => {
      console.warn('[音频播放] 音频解锁失败:', e.name, e.message)
    }).finally(() => {
      URL.revokeObjectURL(url)
    })
  }

  function playNextInQueue() {
    if (audioQueue.length === 0) {
      store.setAiStatus(AI_STATUS.LISTENING)
      activePlay = null
      return
    }
    const pcmBytes = audioQueue.shift()
    if (!pcmBytes || pcmBytes.byteLength === 0) {
      playNextInQueue()
      return
    }
    console.log('[音频播放] 队列取出, PCM数据大小=', pcmBytes.byteLength, 'bytes')

    const wav = pcm16ToWav(pcmBytes, 24000)
    const blob = new Blob([wav], { type: 'audio/wav' })
    const url = URL.createObjectURL(blob)
    const el = getAudioElement()
    const playId = Date.now()
    activePlay = playId

    el.onended = () => {
      URL.revokeObjectURL(url)
      if (activePlay === playId) {
        console.log('[音频播放] 播放完毕，播放下一段')
        playNextInQueue()
      }
    }
    el.onerror = () => {
      const err = el.error
      console.error('[音频播放] error事件: code=', err?.code, 'message=', err?.message)
      URL.revokeObjectURL(url)
      if (activePlay === playId) {
        playNextInQueue()
      }
    }
    el.src = url
    el.load()
    el.play().then(() => {
      console.log('[音频播放] 播放开始成功')
    }).catch(e => {
      console.error('[音频播放] play()被拒绝:', e.name, e.message)
      URL.revokeObjectURL(url)
      if (activePlay === playId) {
        playNextInQueue()
      }
    })
  }

  function queueAudioChunk(audioData) {
    if (!audioData || audioData.byteLength === 0) return
    console.log('[音频播放] 收到音频数据:', audioData.byteLength, 'bytes')
    audioQueue.push(new Uint8Array(audioData))
    if (!activePlay) playNextInQueue()
  }

  function flushAudioPlayback() {
    audioQueue = []
    if (audioEl && !audioEl.paused) {
      audioEl.pause()
    }
    if (audioEl) {
      audioEl.onended = null
      audioEl.onerror = null
      audioEl.src = ''
    }
    activePlay = null
  }

  // --- WebSocket ---
  const { wsStatus, connect: wsConnect, disconnect: wsDisconnect, send, sendBinary } = useWebSocket({
    onJsonMessage: handleMessage,
    onAudioChunk: queueAudioChunk,
    onStatusChange: (status) => { store.wsStatus = status },
    onAuthFailure: async () => {
      // Token expired or invalid — get fresh token from reconnect API
      try {
        const { reconnectInterview } = await import('../services/interviewService.js')
        const { data } = await reconnectInterview(store.interviewId)
        const newToken = data.ws_token
        const newPath = data.ws_url
        sessionStorage.setItem('ws_token', newToken)
        sessionStorage.setItem('ws_url', newPath)
        let wsUrl
        if (newPath.startsWith('ws://') || newPath.startsWith('wss://')) {
          wsUrl = newPath
        } else {
          const apiBase = import.meta.env.VITE_API_BASE_URL || ''
          const wsBase = apiBase.replace(/^http/, 'ws')
          wsUrl = wsBase + newPath
        }
        wsConnect(wsUrl, newToken)
      } catch {
        ElMessage.error('面试已失效，请返回首页重新开始')
        router.push('/dashboard')
      }
    }
  })

  // --- Audio Recorder (manual PTT, no VAD auto-trigger) ---
  const {
    isRecording, isSpeaking,
    isInitialized: micReady,
    init: micInit,
    start: micStart,
    stop: micStop,
    destroy: micDestroy
  } = useAudioRecorder({
    onAudioChunk: (pcmData) => {
      sendBinary(pcmData)
    },
    // No VAD callbacks — manual PTT mode
    externalVAD,
    vadThreshold: 0.01,
    sampleRate: 16000
  })

  // --- Recording duration tracker (max 58s, API limit is 60s) ---
  const MAX_RECORD_SEC = 58
  const recordingDuration = ref(0)
  const micParsing = ref(false)    // true while STT is processing after mic stop
  const isMicActive = ref(false)   // true while user is holding mic button (PTT)
  let recordingTimer = null
  let recordingStartTime = 0

  function startRecordingTimer() {
    recordingDuration.value = 0
    recordingStartTime = Date.now()
    recordingTimer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000)
      recordingDuration.value = elapsed
      if (elapsed >= MAX_RECORD_SEC) {
        // Auto-stop and send
        clearInterval(recordingTimer)
        recordingTimer = null
        stopMic()
        ElMessage.warning(`录音已达 ${MAX_RECORD_SEC} 秒上限，已自动发送`)
      }
    }, 200)
  }

  function clearRecordingTimer() {
    if (recordingTimer) {
      clearInterval(recordingTimer)
      recordingTimer = null
    }
    recordingDuration.value = 0
  }

  // --- Draft bubble (editable STT result before sending) ---
  const draftText = ref('')
  const draftId = ref(null)
  const draftModified = ref(false)  // true when user has edited the draft
  let draftTimer = null
  const DRAFT_AUTO_SEND_MS = 4000

  function clearDraftTimer() {
    if (draftTimer) {
      clearTimeout(draftTimer)
      draftTimer = null
    }
  }

  function removeDraft() {
    clearDraftTimer()
    if (draftId.value !== null) {
      const idx = store.dialogue.findIndex(m => m._draftId === draftId.value)
      if (idx >= 0) store.dialogue.splice(idx, 1)
      draftId.value = null
    }
    draftText.value = ''
  }

  // --- Incoming Message Dispatch ---
  function handleMessage(msg) {
    const { type, data } = msg

    switch (type) {
      case 'session/started':
        console.log('[面试] 会话已开始, 阶段:', data.stage || '初筛', data.message ? '| 消息:' + data.message : '')
        store.currentStage = data.stage || '初筛'
        store.status = INTERVIEW_STATUS.IN_PROGRESS
        if (data.remaining_seconds) remainingSeconds.value = data.remaining_seconds
        if (data.message) store.addMessage('system', data.message)
        break

      case 'user/text_echo':
        console.log('[面试] STT识别结果:', data.text)
        micParsing.value = false   // STT done, clear parsing state
        clearTimeout(micParsingTimer)  // clear safety timeout
        // STT result — show as editable draft bubble, auto-send after delay
        if (data.text && data.text.trim()) {
          removeDraft()
          draftText.value = data.text.trim()
          draftId.value = Date.now()
          draftModified.value = false
          store.dialogue.push({
            role: 'user',
            text: draftText.value,
            time: new Date().toISOString(),
            isDraft: true,
            _draftId: draftId.value,
          })
          // Auto-send after delay (cancelled if user edits)
          draftTimer = setTimeout(() => {
            if (!draftModified.value) {
              confirmDraft()
            }
          }, DRAFT_AUTO_SEND_MS)
        }
        break

      case 'ai/status':
        console.log('[面试] AI状态变更:', data.status)
        store.setAiStatus(data.status)
        if (data.status === AI_STATUS.LISTENING) {
          flushAudioPlayback()
        }
        break

      case 'ai/text':
        {
          let text = data.text || ''
          // Defensive: if the response leaked raw LLM evaluation JSON, extract message
          if (text.trim().startsWith('{') && text.includes('"action"')) {
            try {
              const parsed = JSON.parse(text)
              text = parsed.message || parsed.question_text || text
            } catch { /* keep as-is */ }
          }
          if (data.is_final === false) {
            console.log('[面试] AI文本(流式):', text?.substring(0, 50) + (text?.length > 50 ? '...' : ''))
            store.addMessage('ai', text, true)
          } else {
            console.log('[面试] AI文本(最终):', text)
            store.finalizeMessage('ai')
            if (text && text !== store.dialogue[store.dialogue.length - 1]?.text) {
              store.addMessage('ai', text, false)
            }
          }
        }
        break

      case 'control/stage_change':
        console.log('[面试] 阶段切换:', data.from, '→', data.to, data.message ? '| ' + data.message : '')
        // Cancel any pending draft from previous stage to avoid cross-stage leakage
        removeDraft()
        store.currentStage = data.to
        stageTransition.value = { from: data.from, to: data.to, message: data.message || '' }
        if (data.message) store.addMessage('system', data.message)
        if (data.question) store.addMessage('ai', data.question)
        break

      case 'control/coding_challenge':
        console.log('[面试] 编程题下发:', data.title, '| 语言:', data.language)
        store.setCodingChallenge({
          questionId: data.question_id,
          title: data.title,
          language: data.language,
          description: data.description
        })
        break

      case 'control/coding_submit_response':
        console.log('[面试] 代码评审结果:', data.review?.substring(0, 80) + (data.review?.length > 80 ? '...' : ''))
        if (data.review) store.addMessage('ai', data.review)
        break

      case 'session/resumed':
        console.log('[面试] 会话续接:', data.stage, data.message, '对话条数:', data.dialogue?.length)
        store.currentStage = data.stage || store.currentStage
        store.status = INTERVIEW_STATUS.IN_PROGRESS
        store.setAiStatus(AI_STATUS.LISTENING)  // AI is waiting, not speaking
        if (data.remaining_seconds) remainingSeconds.value = data.remaining_seconds
        // Restore dialogue history from backend
        if (data.dialogue && data.dialogue.length > 0) {
          data.dialogue.forEach(m => {
            store.addMessage(m.role, m.text, false)
          })
        }
        if (data.message) store.addMessage('system', data.message)
        break

      case 'session/end':
        console.log('[面试] 会话结束')
        clearTimeout(endingTimer)
        isEnding.value = false
        isEndingLong.value = false
        store.status = INTERVIEW_STATUS.COMPLETED
        flushAudioPlayback()
        wsDisconnect()
        router.push(`/report/${store.interviewId}`)
        break

      default:
        console.log('[面试] 未知消息类型:', type, data)
    }
  }

  // --- Public API ---
  const stageTransition = ref(null)
  const remainingSeconds = ref(null)
  const isEnding = ref(false)
  const isEndingLong = ref(false)  // true after 10s — show "taking longer" message
  let endingTimer = null
  const ENDING_TIMEOUT_MS = 10000

  async function startInterview(interviewId, wsToken, wsUrl) {
    // Only reset on fresh start; reconnect preserves state via session/resumed
    if (!store.interviewId || store.interviewId !== interviewId) {
      store.resetInterview()
    }
    store.interviewId = interviewId
    store.wsToken = wsToken
    store.wsUrl = wsUrl

    const ok = await micInit()
    if (!ok) {
      ElMessage.warning('无法访问麦克风，请检查权限设置')
    }
    // Pre-unlock audio playback while user gesture is still valid
    unlockAudio()

    wsConnect(wsUrl, wsToken)
  }

  function startMic() {
    console.log('[麦克风] 开始录音')
    // If a draft is visible, discard it (re-record)
    removeDraft()
    isMicActive.value = true
    micParsing.value = false  // clear any stale parsing state
    clearTimeout(micParsingTimer)
    micStart()
    startRecordingTimer()
  }

  function reRecord() {
    // Explicit re-record: discard current draft, start fresh recording
    removeDraft()
    startMic()
  }

  let micParsingTimer = null

  function stopMic() {
    console.log('[麦克风] 停止录音, 时长:', recordingDuration.value + 's')
    isMicActive.value = false
    clearRecordingTimer()
    micStop()
    micParsing.value = true  // Show "parsing" state on mic button
    // Safety timeout: clear parsing state after 15s if no STT result arrives
    clearTimeout(micParsingTimer)
    micParsingTimer = setTimeout(() => {
      if (micParsing.value) {
        console.warn('[麦克风] 解析超时，强制恢复')
        micParsing.value = false
      }
    }, 15000)
    // Signal backend to run STT on accumulated audio
    send({ type: 'user/speech_end', data: { timestamp: Date.now() } })
  }

  function confirmDraft() {
    clearDraftTimer()
    const text = draftText.value.trim()
    if (!text) {
      console.log('[面试] 草稿为空，已移除')
      removeDraft()
      return
    }
    console.log('[面试] 确认发送文本:', text)
    // Replace draft bubble with final message and send
    const idx = store.dialogue.findIndex(m => m._draftId === draftId.value)
    if (idx >= 0) {
      store.dialogue[idx].isDraft = false
      store.dialogue[idx].text = text
    }
    draftId.value = null
    draftText.value = ''
    store.setAiStatus(AI_STATUS.THINKING)  // immediate feedback, prevent double-send
    send({ type: 'user/text', data: { text, timestamp: Date.now() } })
  }

  function updateDraft(newText) {
    draftText.value = newText
    draftModified.value = true  // user edited — cancel auto-send
    clearDraftTimer()
    const idx = store.dialogue.findIndex(m => m._draftId === draftId.value)
    if (idx >= 0) {
      store.dialogue[idx].text = newText
    }
  }

  function sendManualText(text) {
    console.log('[面试] 手动发送文本:', text)
    removeDraft()
    store.addMessage('user', text)
    store.setAiStatus(AI_STATUS.THINKING)  // immediate feedback, prevent double-send
    send({ type: 'user/text', data: { text, timestamp: Date.now() } })
  }

  function submitCode(questionId, code, language) {
    console.log('[面试] 提交代码, 题目ID:', questionId, '语言:', language, '代码长度:', code.length)
    send({
      type: 'control/submit_code',
      data: { question_id: questionId, code, language }
    })
  }

  function endSession() {
    console.log('[面试] 主动结束面试')
    clearRecordingTimer()
    clearDraftTimer()
    isEnding.value = true
    send({ type: 'control/end_session' })
    // If no response within timeout, show "taking longer" message but keep waiting
    endingTimer = setTimeout(() => {
      console.warn('[面试] 结束超时，继续等待')
      isEndingLong.value = true
    }, ENDING_TIMEOUT_MS)
  }

  function closeStageTransition() {
    stageTransition.value = null
  }

  onUnmounted(() => {
    clearRecordingTimer()
    clearDraftTimer()
    clearTimeout(endingTimer)
    flushAudioPlayback()
    micDestroy()
    wsDisconnect()
    // Reset store so other pages don't think interview is still active
    store.resetInterview()
  })

  const stateRefs = storeToRefs(store)

  return {
    currentStage: stateRefs.currentStage,
    dialogue: stateRefs.dialogue,
    aiStatus: stateRefs.aiStatus,
    wsStatus: stateRefs.wsStatus,
    codingChallenge: stateRefs.codingChallenge,
    isMicMuted: stateRefs.isMicMuted,
    interviewId: stateRefs.interviewId,

    stageTransition,
    isRecording,
    isSpeaking,
    micReady,
    micParsing,
    isMicActive,
    recordingDuration,
    MAX_RECORD_SEC,
    draftText,
    draftId,
    draftModified,

    startInterview,
    startMic,
    stopMic,
    reRecord,
    confirmDraft,
    updateDraft,
    sendManualText,
    submitCode,
    endSession,
    remainingSeconds,
    closeStageTransition,
    isEnding,
    isEndingLong
  }
}
