import { defineStore } from 'pinia'
import { ref } from 'vue'
import { AI_STATUS, INTERVIEW_STATUS } from '../utils/constants.js'

export const useInterviewStore = defineStore('interview', () => {
  const interviewId = ref('')
  const wsToken = ref('')
  const wsUrl = ref('')

  const currentStage = ref('初筛')
  const status = ref(INTERVIEW_STATUS.CREATED)
  const aiStatus = ref(AI_STATUS.SPEAKING) // start disabled — mic unlocks after first AI message
  const wsStatus = ref('disconnected') // connecting | connected | reconnecting | disconnected

  const dialogue = ref([]) // { role, text, time, isStreaming? }
  const codingChallenge = ref(null)
  const isMicMuted = ref(false)

  function addMessage(role, text, isStreaming = false) {
    const lastMsg = dialogue.value[dialogue.value.length - 1]
    if (isStreaming && lastMsg && lastMsg.role === role && lastMsg.isStreaming) {
      lastMsg.text += text
    } else if (lastMsg && lastMsg.role === role && lastMsg.isStreaming && !isStreaming) {
      lastMsg.text = text
      lastMsg.isStreaming = false
    } else {
      dialogue.value.push({ role, text, time: new Date().toISOString(), isStreaming })
    }
  }

  function finalizeMessage(role) {
    const lastMsg = dialogue.value[dialogue.value.length - 1]
    if (lastMsg && lastMsg.role === role) {
      lastMsg.isStreaming = false
    }
  }

  function setAiStatus(newStatus) {
    aiStatus.value = newStatus
  }

  function setCodingChallenge(challenge) {
    codingChallenge.value = challenge
  }

  function clearCodingChallenge() {
    codingChallenge.value = null
  }

  function resetInterview() {
    interviewId.value = ''
    wsToken.value = ''
    wsUrl.value = ''
    currentStage.value = '初筛'
    status.value = INTERVIEW_STATUS.CREATED
    aiStatus.value = AI_STATUS.SPEAKING // reset: mic disabled until first AI message
    wsStatus.value = 'disconnected'
    dialogue.value = []
    codingChallenge.value = null
    isMicMuted.value = false
  }

  return {
    interviewId, wsToken, wsUrl,
    currentStage, status, aiStatus, wsStatus,
    dialogue, codingChallenge, isMicMuted,
    addMessage, finalizeMessage, setAiStatus,
    setCodingChallenge, clearCodingChallenge, resetInterview
  }
})
