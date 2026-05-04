<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { AI_STATUS } from '../utils/constants.js'
import { useInterview } from '../composables/useInterview.js'
import { useSileroVAD } from '../composables/useSileroVAD.js'
import CodeEditorPanel from '../components/CodeEditorPanel.vue'
import AudioWaveform from '../components/AudioWaveform.vue'
import AIStatusIndicator from '../components/AIStatusIndicator.vue'
import CountdownTimer from '../components/CountdownTimer.vue'
import StageTransition from '../components/StageTransition.vue'

const route = useRoute()

// --- VAD (kept for potential future use, not used in PTT mode) ---
const {
  detect: vadDetect,
  destroy: vadDestroy
} = useSileroVAD({ sensitivity: 0.5 })

// --- Interview composable ---
const {
  currentStage, dialogue, aiStatus, wsStatus, codingChallenge,
  isMicMuted, stageTransition, isRecording, isSpeaking,
  micParsing, recordingDuration, MAX_RECORD_SEC,
  draftText, draftId, draftModified,
  startInterview, startMic, stopMic, reRecord, confirmDraft, updateDraft, sendManualText,
  isMicActive,
  submitCode, endSession, closeStageTransition
} = useInterview({ externalVAD: vadDetect })

// Mic PTT state — moved to useInterview for unified control
const micEnabled = computed(() => {
  // Mic only available when AI is listening (finished speaking) and no coding challenge
  return aiStatus.value === AI_STATUS.LISTENING && !codingChallenge.value
})
const recordingRemaining = computed(() => Math.max(0, MAX_RECORD_SEC - recordingDuration.value))
const recordingWarnLevel = computed(() => {
  if (recordingRemaining.value <= 3) return 'critical'
  if (recordingRemaining.value <= 10) return 'warning'
  return 'ok'
})

// --- Camera ---
const cameraEnabled = ref(false)
const cameraRef = ref(null)
const showCamera = ref(false)
let cameraStream = null

async function initCamera() {
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({ video: true })
    // Set flags first so the video element renders, then attach stream
    cameraEnabled.value = true
    showCamera.value = true
    await nextTick()
    if (cameraRef.value) {
      cameraRef.value.srcObject = cameraStream
    }
  } catch { cameraEnabled.value = false }
}

function toggleCamera() { showCamera.value = !showCamera.value }

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop())
    cameraStream = null
  }
  cameraEnabled.value = false
}

// --- AI Avatar ---
const avatarPresets = [
  { name: '面试官A', style: '亲和', bgColor: '#EBF0F7', hairColor: '#2B3A67', skinColor: '#F5E6D3' },
  { name: '面试官B', style: '严肃', bgColor: '#F0EEE8', hairColor: '#3C3C3C', skinColor: '#E8D5C0' }
]
const avatarScene = ref('简洁白墙背景')
const avatarPreset = ref(avatarPresets[0])

onMounted(async () => {
  avatarPreset.value = avatarPresets[Math.floor(Math.random() * avatarPresets.length)]
  avatarScene.value = Math.random() > 0.5 ? '简洁白墙背景' : '虚化书架背景'
  initCamera()

  const interviewId = route.params.id
  const wsToken = sessionStorage.getItem('ws_token')
  const wsPath = sessionStorage.getItem('ws_url')

  if (interviewId && wsToken && wsPath) {
    // ws_url from API may be a full URL (wss://host/path) or a relative path (/ws/interview/xxx)
    let wsUrl
    if (wsPath.startsWith('ws://') || wsPath.startsWith('wss://')) {
      wsUrl = wsPath
    } else {
      const apiBase = import.meta.env.VITE_API_BASE_URL || ''
      const wsBase = apiBase.replace(/^http/, 'ws')
      wsUrl = wsBase + wsPath
    }
    startInterview(interviewId, wsToken, wsUrl)
  }
})

onUnmounted(() => {
  stopCamera()
  vadDestroy()
})

// --- Manual text ---
const manualText = ref('')
function handleSendText() {
  const text = manualText.value.trim()
  if (!text) return
  sendManualText(text)
  manualText.value = ''
}

// --- End interview ---
async function handleEndInterview() {
  try {
    await ElMessageBox.confirm('确定结束面试吗？结束后不可恢复', '结束面试', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    })
    endSession()
  } catch { /* cancelled */ }
}

// --- Code Editor ---
const codeValue = ref('')
const isCodeSubmitted = ref(false)

function handleCodeSubmit(code) {
  if (!codingChallenge.value) return
  submitCode(
    codingChallenge.value.questionId,
    code,
    codingChallenge.value.language
  )
  isCodeSubmitted.value = true
}

function handleContinueInterview() {
  codingChallenge.value = null
  codeValue.value = ''
  isCodeSubmitted.value = false
}

// --- Auto scroll ---
const dialogueContainer = ref(null)
watch(() => dialogue.value?.length ?? 0, async () => {
  await nextTick()
  if (dialogueContainer.value) {
    dialogueContainer.value.scrollTop = dialogueContainer.value.scrollHeight
  }
})
// Also scroll on deep changes (streaming text updates)
watch(() => dialogue.value, async () => {
  await nextTick()
  if (dialogueContainer.value) {
    dialogueContainer.value.scrollTop = dialogueContainer.value.scrollHeight
  }
}, { deep: true })

const isCodingActive = computed(() => !!codingChallenge.value)
const isAiSpeaking = computed(() => aiStatus === AI_STATUS.SPEAKING)

function handleMicToggle() {
  if (isMicActive.value) {
    stopMic()   // sets isMicActive=false internally
  } else if (micEnabled.value) {
    startMic()  // sets isMicActive=true internally
  }
}
</script>

<template>
  <div class="interview-room" :class="{ 'coding-active': isCodingActive }">
    <!-- Header -->
    <header class="room-header">
      <div class="header-left">
        <span class="stage-name">{{ currentStage }}</span>
        <CountdownTimer />
      </div>
      <div class="header-center"></div>
      <div class="header-right">
        <el-button v-if="cameraEnabled && !isCodingActive" text size="small" @click="toggleCamera">
          {{ showCamera ? '隐藏摄像头' : '显示摄像头' }}
        </el-button>
        <el-button type="danger" size="small" @click="handleEndInterview">结束面试</el-button>
      </div>
    </header>

    <!-- Body -->
    <div class="room-body">
      <!-- Dialogue -->
      <div class="dialogue-area" ref="dialogueContainer">
        <div v-if="!dialogue.length" class="dialogue-empty">
          <el-icon :size="32" color="#D0D5DD"><ChatDotRound /></el-icon>
          <p>面试即将开始，请稍候...</p>
        </div>
        <div v-for="(msg, idx) in dialogue" :key="idx" class="message-row" :class="msg.role">
          <div class="msg-meta">
            <span class="msg-role-tag" :class="msg.role">
              {{ msg.role === 'ai' ? '面试官' : msg.role === 'system' ? '系统' : '我' }}
            </span>
            <span class="msg-time">
              {{ new Date(msg.time).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }}
            </span>
          </div>
          <!-- Draft bubble: editable before sending -->
          <div v-if="msg.isDraft" class="msg-text draft-bubble">
            <el-input
              :model-value="draftText"
              type="textarea"
              :rows="2"
              placeholder="编辑识别文字..."
              @input="updateDraft($event)"
              @keyup.enter.ctrl="confirmDraft()"
            />
            <div class="draft-actions">
              <span class="draft-timer">
                {{ draftModified ? '可手动发送或重新回答' : '即将自动发送...' }}
              </span>
              <el-button size="small" plain @click="reRecord()">重新回答</el-button>
              <el-button size="small" type="primary" @click="confirmDraft()">发送</el-button>
            </div>
          </div>
          <!-- Normal message -->
          <div v-else class="msg-text" :class="{ streaming: msg.isStreaming }">
            {{ msg.text }}
            <span v-if="msg.isStreaming" class="cursor-blink">|</span>
          </div>
        </div>
      </div>

      <!-- Right Panel -->
      <div class="right-panel" v-if="!isCodingActive">
        <div v-if="cameraEnabled && showCamera" class="camera-panel">
          <video ref="cameraRef" autoplay muted playsinline class="camera-video"></video>
        </div>
        <div class="avatar-panel" :style="{ background: avatarPreset.bgColor }">
          <div class="avatar-scene-label">{{ avatarScene }}</div>
          <div class="avatar-character" :class="aiStatus">
            <div class="avatar-head">
              <div class="avatar-hair" :style="{ background: avatarPreset.hairColor }"></div>
              <div class="avatar-face" :style="{ background: avatarPreset.skinColor }">
                <div class="avatar-eyes">
                  <span class="eye" :class="{ thinking: aiStatus === AI_STATUS.THINKING }"></span>
                  <span class="eye" :class="{ thinking: aiStatus === AI_STATUS.THINKING }"></span>
                </div>
                <div class="avatar-mouth" :class="{ speaking: isAiSpeaking }"></div>
              </div>
            </div>
            <div class="avatar-body" :style="{ background: avatarPreset.hairColor }"></div>
          </div>
          <div class="avatar-name">{{ avatarPreset.name }}</div>
          <div class="avatar-style-tag">{{ avatarPreset.style }}</div>
        </div>
      </div>

      <!-- Code Editor Panel (Monaco) -->
      <CodeEditorPanel
        v-if="isCodingActive"
        :title="codingChallenge?.title || '编程题'"
        :description="codingChallenge?.description || ''"
        :language="codingChallenge?.language || 'python'"
        :readOnly="isCodeSubmitted"
        v-model="codeValue"
        @submit="handleCodeSubmit"
        @continue="handleContinueInterview"
      />
    </div>

    <!-- Footer -->
    <footer class="room-footer">
      <div class="footer-left">
        <!-- PTT Mic Button with countdown -->
        <div class="mic-area">
          <el-button
            :type="isMicActive ? 'danger' : micParsing ? '' : micEnabled ? 'primary' : 'info'"
            :icon="isMicActive ? 'VideoPause' : micParsing ? 'Loading' : 'Microphone'"
            circle
            size="large"
            :disabled="micParsing || (!isMicActive && !micEnabled)"
            :class="['mic-btn', { 'mic-recording': isMicActive, 'mic-parsing': micParsing, 'mic-warn': isMicActive && recordingWarnLevel === 'warning', 'mic-critical': isMicActive && recordingWarnLevel === 'critical' }]"
            @click="handleMicToggle"
          />
          <span v-if="isMicActive" class="mic-countdown" :class="'countdown-' + recordingWarnLevel">
            {{ recordingRemaining }}s
          </span>
          <span v-if="micParsing" class="mic-parsing-label">解析中...</span>
        </div>
        <AIStatusIndicator :status="aiStatus" />
        <AudioWaveform :active="isRecording" />
      </div>
      <div class="footer-right">
        <el-input
          v-model="manualText"
          placeholder="或手动输入文字..."
          size="small"
          style="width: 220px"
          @keyup.enter="handleSendText"
        >
          <template #append>
            <el-button @click="handleSendText" :disabled="!manualText.trim()">发送</el-button>
          </template>
        </el-input>
      </div>
    </footer>

    <StageTransition
      v-if="stageTransition"
      :from="stageTransition.from"
      :to="stageTransition.to"
      :message="stageTransition.message"
      :autoClose="1500"
      @close="closeStageTransition"
    />
  </div>
</template>

<style scoped>
.interview-room {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 48px - 38px);
  background: var(--color-bg);
  overflow: hidden;
}

/* Header */
.room-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 48px;
  padding: 0 20px;
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 20px; }
.header-center { display: flex; align-items: center; gap: 16px; }
.header-right { display: flex; align-items: center; gap: 12px; }
.stage-name { font-size: 14px; font-weight: 600; color: var(--color-accent); }
.vad-control { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--color-text-secondary); }
.vad-label { font-weight: 500; }

/* Body */
.room-body { flex: 1; display: flex; overflow: hidden; }

/* Dialogue */
.dialogue-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  background: var(--color-card);
  margin: 8px 0 0 8px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
}
.dialogue-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; color: var(--color-text-secondary); gap: 12px; font-size: 14px;
}
.message-row { margin-bottom: 20px; }
.msg-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.msg-role-tag {
  display: inline-block; padding: 1px 8px; font-size: 12px; font-weight: 500; border-radius: 2px;
}
.msg-role-tag.ai { background: rgba(43, 58, 103, 0.08); color: var(--color-accent); }
.msg-role-tag.user { background: rgba(107, 114, 128, 0.08); color: var(--color-text-secondary); }
.msg-role-tag.system { background: rgba(217, 163, 74, 0.12); color: #D9A34A; }
.msg-time { font-size: 11px; color: var(--color-text-secondary); }
.msg-text {
  font-size: 14px; color: var(--color-text); line-height: 1.7;
  padding: 10px 14px; background: var(--color-border-light); border-radius: 2px;
  border-left: 2px solid transparent;
}
.message-row.ai .msg-text { border-left-color: var(--color-accent); }
.message-row.user .msg-text { border-left-color: var(--color-text-secondary); }
.message-row.system .msg-text { border-left-color: #D9A34A; text-align: center; font-size: 13px; }
.cursor-blink { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }

/* Draft Bubble */
.draft-bubble {
  border: 2px dashed var(--color-accent) !important;
  background: rgba(43, 58, 103, 0.03) !important;
}
.draft-actions {
  display: flex; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 8px;
}
.draft-timer { font-size: 11px; color: var(--color-text-secondary); }

/* PTT Mic Button */
.mic-area { position: relative; display: flex; align-items: center; }
.mic-btn { transition: all 0.2s; }
.mic-recording {
  animation: mic-pulse 1s ease-in-out infinite;
  box-shadow: 0 0 12px rgba(194, 122, 61, 0.5);
}
.mic-warn { box-shadow: 0 0 14px rgba(230, 162, 60, 0.7); }
.mic-critical { animation: mic-pulse 0.5s ease-in-out infinite; box-shadow: 0 0 18px rgba(245, 63, 63, 0.7); }
.mic-parsing {
  animation: mic-pulse 1.5s ease-in-out infinite;
  box-shadow: 0 0 10px rgba(160, 160, 160, 0.4);
}
.mic-parsing-label {
  position: absolute; bottom: -20px; left: 50%; transform: translateX(-50%);
  font-size: 11px; color: var(--color-text-secondary); white-space: nowrap;
}
.mic-countdown {
  position: absolute; top: -8px; right: -8px;
  min-width: 28px; height: 20px; line-height: 20px;
  border-radius: 10px; font-size: 11px; font-weight: 600; text-align: center;
  padding: 0 5px; pointer-events: none; user-select: none;
}
.countdown-ok { background: rgba(43,58,103,0.85); color: #fff; }
.countdown-warning { background: rgba(230,162,60,0.9); color: #fff; }
.countdown-critical { background: rgba(245,63,63,0.9); color: #fff; animation: countdown-flash 0.6s step-end infinite; }
@keyframes countdown-flash { 50% { opacity: 0.5; } }
@keyframes mic-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}

/* Right Panel */
.right-panel { width: 240px; padding: 12px; display: flex; flex-direction: column; gap: 12px; flex-shrink: 0; }
.camera-panel { width: 216px; height: 150px; background: #000; border-radius: 4px; overflow: hidden; }
.camera-video { width: 100%; height: 100%; object-fit: cover; }

/* AI Avatar */
.avatar-panel {
  width: 216px; background: var(--color-card); border: 1px solid var(--color-border);
  border-radius: 4px; padding: 16px; text-align: center; position: relative;
}
.avatar-scene-label { font-size: 10px; color: var(--color-text-secondary); position: absolute; top: 6px; right: 10px; }
.avatar-character { display: flex; flex-direction: column; align-items: center; transition: transform 0.3s ease; }
.avatar-character.listening { transform: translateY(0); }
.avatar-character.thinking { transform: translateY(2px); }
.avatar-character.speaking { animation: avatar-nod 0.6s ease-in-out infinite alternate; }
.avatar-head { width: 56px; height: 64px; position: relative; }
.avatar-hair { width: 60px; height: 28px; border-radius: 30px 30px 0 0; position: absolute; top: 0; left: -2px; }
.avatar-face { width: 56px; height: 42px; border-radius: 4px 4px 20px 20px; position: absolute; top: 20px; }
.avatar-eyes { display: flex; gap: 10px; justify-content: center; padding-top: 12px; }
.eye { width: 6px; height: 6px; border-radius: 50%; background: #333; display: block; }
.eye.thinking { animation: look-away 0.8s ease-in-out infinite alternate; }
.avatar-mouth { width: 14px; height: 5px; border-radius: 0 0 7px 7px; background: #C27A3D; margin: 6px auto 0; transition: all 0.2s; }
.avatar-mouth.speaking { width: 10px; height: 8px; border-radius: 50%; animation: mouth-talk 0.3s ease-in-out infinite alternate; }
.avatar-body { width: 90px; height: 36px; border-radius: 20px 20px 4px 4px; margin-top: -2px; }
.avatar-name { font-size: 13px; font-weight: 500; color: var(--color-text); margin-top: 12px; }
.avatar-style-tag { font-size: 11px; color: var(--color-text-secondary); }
@keyframes avatar-nod { 0% { transform: translateY(0); } 100% { transform: translateY(-3px); } }
@keyframes look-away { 0% { transform: translateX(0); } 100% { transform: translateX(3px); } }
@keyframes mouth-talk { 0% { height: 4px; } 100% { height: 10px; } }

/* Footer */
.room-footer {
  display: flex; justify-content: space-between; align-items: center;
  height: 52px; padding: 0 20px; background: var(--color-card);
  border-top: 1px solid var(--color-border); flex-shrink: 0;
}
.footer-left { display: flex; align-items: center; gap: 10px; }
.footer-right { display: flex; align-items: center; }

/* ── Mobile (≤768px) ── */
@media (max-width: 768px) {
  .interview-room {
    height: calc(100vh - 40px - 56px); /* header 40 + bottom tabs 56 */
  }

  .room-header {
    height: 40px;
    padding: 0 10px;
  }
  .header-left { gap: 10px; }
  .header-right { gap: 6px; }
  .stage-name { font-size: 13px; }
  .vad-control { display: none; }

  .room-body {
    flex-direction: column;
    position: relative;
  }

  .dialogue-area {
    flex: 1;
    padding: 12px 10px;
    overflow-y: auto;
  }
  .msg-text {
    font-size: 14px;
    padding: 8px 10px;
  }
  .empty-state {
    font-size: 13px;
    gap: 8px;
  }

  /* Right panel → floating overlay */
  .right-panel {
    position: absolute;
    top: 8px;
    right: 8px;
    width: auto;
    padding: 0;
    background: transparent;
    border: none;
    gap: 0;
    z-index: 10;
  }
  .camera-panel {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.8);
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  }
  .camera-video {
    border-radius: 50%;
    object-fit: cover;
  }

  .avatar-panel {
    display: none;
  }

  /* Footer */
  .room-footer {
    height: auto;
    padding: 8px 10px;
    flex-wrap: wrap;
    gap: 8px;
  }
  .footer-left {
    flex: 1;
    justify-content: center;
  }
  .footer-right {
    width: 100%;
  }
  .footer-right .el-input {
    width: 100% !important;
    min-width: 0 !important;
  }

  /* Mic button larger for touch */
  .mic-area .el-button {
    width: 56px !important;
    height: 56px !important;
  }

  /* Draft bubble full width */
  .message-row.draft .msg-text {
    max-width: 100%;
  }
  .draft-actions {
    flex-wrap: wrap;
    gap: 6px;
  }
}
</style>
