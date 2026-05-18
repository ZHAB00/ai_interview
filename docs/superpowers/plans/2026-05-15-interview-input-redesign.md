# 面试输入区重设计 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将面试页底部输入区从"麦克风左 + 小输入框右"的分离布局改为统一的 ChatGPT 风格输入栏（麦克风 + textarea + 发送），桌面端和手机端统一设计，同时加入互斥逻辑、发送反馈和快捷回复。

**Architecture:** 改动集中在 `InterviewRoom.vue` 的 <footer> 模板和样式，`useInterview.js` 增加少量辅助状态，`constants.js` 新增一个常量。WS 通信、语音录制、消息展示均不改动。输入禁用态复用现有 `aiStatus` 驱动。

**Tech Stack:** Vue 3 Composition API + Element Plus + scoped CSS

---

## 文件结构

| 文件 | 角色 |
|------|------|
| `vue_ai_interview/src/utils/constants.js` | 新增 `QUICK_REPLIES` 常量 |
| `vue_ai_interview/src/composables/useInterview.js` | 新增 `cancelMicOnTyping()`，暴露 `isMicActive` |
| `vue_ai_interview/src/views/InterviewRoom.vue` | 重写 `<footer>` 模板 + 全部 footer 样式 + 交互逻辑 |

---

### Task 1: 添加 QUICK_REPLIES 常量

**文件:**
- 修改: `vue_ai_interview/src/utils/constants.js`

- [ ] **Step 1: 在 constants.js 末尾添加常量**

```js
export const QUICK_REPLIES = [
  '可以再说一遍吗',
  '请换一种问法',
  '跳过这个问题'
]
```

- [ ] **Step 2: 在 InterviewRoom.vue 中导入**

在现有 import 行（第5行）追加 `QUICK_REPLIES`：

```js
import { AI_STATUS, QUICK_REPLIES } from '../utils/constants.js'
```

- [ ] **Step 3: Commit**

```bash
git add vue_ai_interview/src/utils/constants.js vue_ai_interview/src/views/InterviewRoom.vue
git commit -m "feat: add QUICK_REPLIES constant for interview input area"
```

---

### Task 2: useInterview 添加打字取消录音逻辑

**文件:**
- 修改: `vue_ai_interview/src/composables/useInterview.js`

- [ ] **Step 1: 新增 `cancelMicOnTyping` 函数**

在 `useInterview` 函数体内，`sendManualText` 之前（约第459行前），添加：

```js
function cancelMicOnTyping() {
  // When user starts typing, cancel any active recording
  if (isMicActive.value) {
    console.log('[麦克风] 打字取消录音')
    isMicActive.value = false
    clearRecordingTimer()
    micStop()
    micParsing.value = false
    clearTimeout(micParsingTimer)
  }
}
```

- [ ] **Step 2: 在 return 对象中暴露 `cancelMicOnTyping`**

在 return 对象中（约第520行 `isMicActive` 之后）添加：

```js
cancelMicOnTyping,
```

完整的 return 对象变更区域：

```js
isMicActive,
cancelMicOnTyping,
recordingDuration,
```

- [ ] **Step 3: Commit**

```bash
git add vue_ai_interview/src/composables/useInterview.js
git commit -m "feat: add cancelMicOnTyping for voice/text mutual exclusion"
```

---

### Task 3: 重写 InterviewRoom.vue footer 模板

**文件:**
- 修改: `vue_ai_interview/src/views/InterviewRoom.vue`

- [ ] **Step 1: 在 `<script setup>` 中新增响应式状态**

在第129行 `const manualText = ref('')` 之后添加：

```js
// --- Quick reply ---
function handleQuickReply(text) {
  manualText.value = text
}
```

替换 `handleSendText` 函数（约第130-135行）：

```js
function handleSendText() {
  const text = manualText.value.trim()
  if (!text) return
  // Mutual exclusion: cancel any active recording
  cancelMicOnTyping()
  sendManualText(text)
  manualText.value = ''
}

function handleInputFocus() {
  cancelMicOnTyping()
}

function handleTextareaKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSendText()
  }
}
```

需要从 `useInterview` 解构中引入 `cancelMicOnTyping`。在现有的解构语句（第24-33行）中添加：

```js
const {
  currentStage, dialogue, aiStatus, wsStatus, codingChallenge,
  isMicMuted, stageTransition, isRecording, isSpeaking,
  micParsing, recordingDuration, MAX_RECORD_SEC,
  draftText, draftId, draftModified,
  startInterview, startMic, stopMic, reRecord, confirmDraft, updateDraft, sendManualText,
  isMicActive, remainingSeconds, cancelMicOnTyping,
  submitCode, endSession, closeStageTransition,
  isEnding, isEndingLong
} = useInterview({ externalVAD: vadDetect })
```

- [ ] **Step 2: 新增计算属性用于输入禁用判断**

在 `isAiSpeaking` 之后（约第189行后）添加：

```js
const isInputDisabled = computed(() => {
  return aiStatus.value !== AI_STATUS.LISTENING || !!codingChallenge.value
})
```

- [ ] **Step 3: 替换 footer 模板**

将第298-333行的整个 `<footer>` 块替换为：

```html
<!-- Footer -->
<footer class="room-footer">
  <!-- Quick reply chips: only when AI is listening and not coding -->
  <div v-if="!isInputDisabled && !isMicActive" class="quick-replies">
    <span
      v-for="(reply, idx) in QUICK_REPLIES"
      :key="idx"
      class="quick-reply-chip"
      @click="handleQuickReply(reply)"
    >{{ reply }}</span>
  </div>

  <!-- Unified input bar -->
  <div class="input-bar" :class="{ 'input-disabled': isInputDisabled, 'input-recording': isMicActive }">
    <!-- Mic button -->
    <div class="mic-area">
      <el-button
        :type="isMicActive ? 'danger' : micParsing ? '' : micEnabled ? 'primary' : 'info'"
        :icon="isMicActive ? 'VideoPause' : micParsing ? 'Loading' : 'Microphone'"
        circle
        :disabled="micParsing || isInputDisabled || (!isMicActive && !micEnabled)"
        :class="['mic-btn', { 'mic-recording': isMicActive, 'mic-parsing': micParsing, 'mic-warn': isMicActive && recordingWarnLevel === 'warning', 'mic-critical': isMicActive && recordingWarnLevel === 'critical' }]"
        @click="handleMicToggle"
      />
      <span v-if="isMicActive" class="mic-countdown" :class="'countdown-' + recordingWarnLevel">
        {{ recordingRemaining }}s
      </span>
      <span v-if="micParsing" class="mic-parsing-label">解析中...</span>
    </div>

    <!-- Textarea -->
    <textarea
      ref="inputTextareaRef"
      v-model="manualText"
      class="input-textarea"
      :placeholder="isInputDisabled ? '面试官正在回复...' : isMicActive ? '文字输入已锁定（录音中）' : '输入你的回答，或点击麦克风语音输入...'"
      :disabled="isInputDisabled || isMicActive"
      :rows="2"
      @focus="handleInputFocus"
      @keydown="handleTextareaKeydown"
    ></textarea>

    <!-- Send button -->
    <el-button
      type="primary"
      :disabled="isInputDisabled || isMicActive || !manualText.trim()"
      :loading="isInputDisabled && !isMicActive"
      class="send-btn"
      @click="handleSendText"
    >
      {{ isInputDisabled && !isMicActive ? '回复中' : '发送' }}
    </el-button>
  </div>

  <!-- Hint text -->
  <div class="input-hint" v-if="!isInputDisabled && !isMicActive">
    Enter 发送 · Shift+Enter 换行
  </div>
</footer>
```

注意：`mic-btn` 的倒计时和解析标签需要包含在 `.input-bar` 内但在 flex 流中合适的位置。调整后将倒计时直接跟在麦克风按钮之后。

- [ ] **Step 4: 在 script 中新增 template ref**

```js
const inputTextareaRef = ref(null)
```

放在 `const manualText = ref('')` 之后即可。

- [ ] **Step 5: Commit**

```bash
git add vue_ai_interview/src/views/InterviewRoom.vue
git commit -m "feat: rewrite footer template with unified input bar, quick replies, and mutual exclusion"
```

---

### Task 4: 重写 footer 样式（桌面端 + 手机端）

**文件:**
- 修改: `vue_ai_interview/src/views/InterviewRoom.vue`

- [ ] **Step 1: 替换 footer CSS 部分（第530-537行）**

将现有的 `.room-footer` 到 `.footer-right` 样式（第530-537行）替换为：

```css
/* Footer */
.room-footer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 20px 12px;
  background: var(--color-card);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

/* Quick Reply Chips */
.quick-replies {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.quick-reply-chip {
  display: inline-block;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--color-accent);
  background: rgba(43, 58, 103, 0.06);
  border: 1px solid rgba(43, 58, 103, 0.12);
  border-radius: 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s, border-color 0.15s;
}
.quick-reply-chip:hover {
  background: rgba(43, 58, 103, 0.12);
  border-color: rgba(43, 58, 103, 0.25);
}

/* Unified Input Bar */
.input-bar {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 10px 14px;
  background: var(--color-card);
  border: 2px solid var(--color-accent);
  border-radius: 12px;
  transition: border-color 0.2s, opacity 0.2s;
}
.input-bar.input-disabled {
  border-color: var(--color-border);
  opacity: 0.6;
}
.input-bar.input-recording {
  border-color: #e53e3e;
}

/* Mic button inside input bar */
.input-bar .mic-btn {
  flex-shrink: 0;
}

/* Mic countdown badge (positioned relative to input-bar) */
.mic-countdown {
  position: absolute;
  top: -8px;
  right: -8px;
  min-width: 28px;
  height: 20px;
  line-height: 20px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  text-align: center;
  padding: 0 5px;
  pointer-events: none;
  user-select: none;
}
.mic-parsing-label {
  position: absolute;
  bottom: -18px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  color: var(--color-text-secondary);
  white-space: nowrap;
}

/* Textarea */
.input-textarea {
  flex: 1;
  min-height: 24px;
  height: 48px;
  max-height: 150px;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.6;
  padding: 4px 0;
  background: transparent;
  color: var(--color-text);
}
.input-textarea::placeholder {
  color: var(--color-text-secondary);
}
.input-textarea:disabled {
  color: #999;
  cursor: not-allowed;
}

/* Send button */
.send-btn {
  flex-shrink: 0;
}

/* Hint */
.input-hint {
  text-align: right;
  font-size: 10px;
  color: #b0b0b0;
  padding-right: 4px;
}
```

- [ ] **Step 2: 保留 mic 动画 keyframes（不变，约431-460行的 CSS 保留）**

确认 `.mic-btn`、`.mic-recording`、`.mic-warn`、`.mic-critical`、`.mic-parsing`、`.countdown-*`、`@keyframes mic-pulse` 等样式保留在原位置（Task 3中 mic 按钮仍使用这些类名）。

- [ ] **Step 3: 更新手机端 @media 中的 footer 样式**

在 `@media (max-width: 768px)` 块内（约第601-633行），将现有的 footer 和 mic 部分替换为：

```css
/* Footer — unified bar, no wrap */
.room-footer {
  padding: 6px 8px 8px;
  gap: 6px;
}

.quick-replies {
  gap: 6px;
  flex-wrap: nowrap;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.quick-replies::-webkit-scrollbar { display: none; }
.quick-reply-chip {
  flex-shrink: 0;
  font-size: 11px;
  padding: 3px 10px;
}

.input-bar {
  padding: 6px 10px;
  gap: 6px;
  border-radius: 10px;
}

.input-textarea {
  height: 36px;
  min-height: 20px;
  max-height: 100px;
  font-size: 13px;
}

.input-hint {
  font-size: 9px;
  padding-right: 2px;
}

/* Mic button larger for touch */
.input-bar .mic-btn {
  width: 42px !important;
  height: 42px !important;
}
```

同时**删除**旧手机端 footer 中关于 `.footer-left`、`.footer-right`、`.footer-right .el-input`、`.mic-area .el-button` 的规则（约第608-624行），这些已不存在。

- [ ] **Step 4: Commit**

```bash
git add vue_ai_interview/src/views/InterviewRoom.vue
git commit -m "style: unified input bar styles for desktop and mobile"
```

---

### Task 5: 清理和微调

**文件:**
- 修改: `vue_ai_interview/src/views/InterviewRoom.vue`

- [ ] **Step 1: 移除不再需要的导入和组件**

在 `<script setup>` 中：
- 移除 `AIStatusIndicator` 导入（第10行）—— 如果不再在 footer 中显示，可以移除。但检查后确认它还被使用... 实际上在模板中 `<AIStatusIndicator :status="aiStatus" />` 在旧的 footer-left 中。新设计中没有显式放置 AIStatusIndicator。我们需要决定要不要保留它。

决策：保留 `AIStatusIndicator` 导入，但在 input bar 中不显示它。如果以后需要在其他地方显示 AI 状态，导入还在。或者：把它放在 input bar 的 hint 行左边。

实际上，简化起见：**移除** `<AIStatusIndicator>` 的使用，因为 `.input-bar.input-disabled` 的视觉反馈 + placeholder 文字已经足够告知用户 AI 状态。`AudioWaveform` 同理移除。

- [ ] **Step 2: 移除模板中的旧组件引用**

从 import 中移除（可选保留 import 供将来使用，但遵循 YAGNI 原则移除）：

```js
// 删除这两行
import AudioWaveform from '../components/AudioWaveform.vue'
import AIStatusIndicator from '../components/AIStatusIndicator.vue'
```

注意：如果这两个组件在别处被引用，保留导入。检查当前文件——它们只在旧 footer 中使用，可以安全移除导入。

- [ ] **Step 3: 验证 dev server 编译通过**

```bash
cd vue_ai_interview && npx vite build --mode development 2>&1 | tail -20
```

期望：Build successful，无编译错误。

- [ ] **Step 4: Commit**

```bash
git add vue_ai_interview/src/views/InterviewRoom.vue
git commit -m "chore: remove unused AIStatusIndicator and AudioWaveform from interview room"
```

---

## 验证清单

实现完成后，逐项检查：

1. **桌面端 (>768px)**
   - [ ] 底部显示统一输入栏：麦克风按钮 + textarea + 发送按钮
   - [ ] 输入栏上方有 3 个快捷回复 chip
   - [ ] textarea 初始 2 行高，可自动扩展
   - [ ] Enter 发送，Shift+Enter 换行
   - [ ] AI 说话时整栏灰色禁用，按钮显示 "回复中" + spinner
   - [ ] 录音时 textarea 禁用，placeholder 变为 "文字输入已锁定"
   - [ ] 打字时自动取消录音

2. **手机端 (≤768px)**
   - [ ] 输入栏一行不换行
   - [ ] 快捷回复 chip 横向滚动
   - [ ] 元素尺寸等比缩小

3. **不影响已有功能**
   - [ ] 语音录音 → STT 识别 → draft bubble 编辑流程正常
   - [ ] 编程题面板切换正常
   - [ ] 结束面试流程正常
   - [ ] 阶段切换正常
