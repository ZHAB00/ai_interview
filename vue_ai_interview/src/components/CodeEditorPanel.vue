<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import loader from '@monaco-editor/loader'

const props = defineProps({
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  language: { type: String, default: 'python' },
  modelValue: { type: String, default: '' },
  readOnly: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue', 'submit', 'continue'])

const editorContainer = ref(null)
let editor = null
let monacoInstance = null
const editorReady = ref(false)
const submitting = ref(false)

function monacoLang(lang) {
  const map = {
    python: 'python',
    javascript: 'javascript',
    typescript: 'typescript',
    java: 'java',
    go: 'go',
    cpp: 'cpp',
    c: 'c',
    rust: 'rust',
    sql: 'sql',
    html: 'html',
    css: 'css'
  }
  return map[lang?.toLowerCase()] || 'plaintext'
}

function handleSubmit() {
  const code = editor?.getValue() || ''
  if (!code.trim()) return
  emit('submit', code)
}

function handleContinue() {
  emit('continue')
}

onMounted(async () => {
  loader.config({
    paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' }
  })

  monacoInstance = await loader.init()

  if (!editorContainer.value) return

  const lang = monacoLang(props.language)

  editor = monacoInstance.editor.create(editorContainer.value, {
    value: props.modelValue,
    language: lang,
    theme: 'vs-dark',
    fontSize: 14,
    fontFamily: 'Consolas, Monaco, "Courier New", monospace',
    lineNumbers: 'on',
    minimap: { enabled: false },
    automaticLayout: true,
    readOnly: props.readOnly,
    scrollBeyondLastLine: false,
    tabSize: 2,
    wordWrap: 'on'
  })

  editor.onDidChangeModelContent(() => {
    emit('update:modelValue', editor.getValue())
  })

  editorReady.value = true
})

onUnmounted(() => {
  editor?.dispose()
})

watch(() => props.language, (newLang) => {
  if (editor && monacoInstance) {
    monacoInstance.editor.setModelLanguage(editor.getModel(), monacoLang(newLang))
  }
})

watch(() => props.readOnly, (val) => {
  editor?.updateOptions({ readOnly: val })
})

watch(() => props.modelValue, (val) => {
  const current = editor?.getValue()
  if (val !== current) {
    editor?.setValue(val || '')
  }
})
</script>

<template>
  <div class="code-editor-panel">
    <div class="ce-header">
      <div class="ce-header-left">
        <h4>{{ title || '编程题' }}</h4>
        <el-tag size="small">{{ language }}</el-tag>
      </div>
    </div>

    <div v-if="description" class="ce-description">
      <p>{{ description }}</p>
    </div>

    <div ref="editorContainer" class="ce-editor"></div>

    <div class="ce-actions" v-if="!readOnly">
      <el-button type="primary" :disabled="!modelValue?.trim()" :loading="submitting" @click="handleSubmit">
        提交并评审
      </el-button>
      <el-button @click="handleContinue">继续面试</el-button>
    </div>

    <div class="ce-actions" v-else>
      <el-button type="primary" @click="handleContinue">继续面试</el-button>
    </div>
  </div>
</template>

<style scoped>
.code-editor-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #1E1E1E;
  border-left: 1px solid var(--color-border);
}

.ce-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.ce-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ce-header h4 {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
}

.ce-description {
  padding: 12px 16px;
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}
.ce-description p {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.ce-editor {
  flex: 1;
  min-height: 200px;
}

.ce-actions {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-card);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}
</style>
