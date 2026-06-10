import { ref, onUnmounted } from 'vue'
import { WS_RECONNECT_MAX, WS_RECONNECT_INTERVALS } from '../utils/constants.js'

/**
 * WebSocket connection for real-time interview communication.
 * @param {object} options
 * @param {function} options.onJsonMessage - receives parsed JSON message { type, data }
 * @param {function} options.onAudioChunk - receives ArrayBuffer audio data for playback
 * @param {function} options.onStatusChange - receives status string
 */
export function useWebSocket(options = {}) {
  const {
    onJsonMessage = () => {},
    onAudioChunk = () => {},
    onStatusChange = () => {},
    onAuthFailure = null,  // called when WS closes with 4001 (auth failed)
    onInterviewEnded = null,  // called when WS closes with 4000 (interview ended)
  } = options

  const wsStatus = ref('disconnected') // connecting | connected | reconnecting | disconnected
  let ws = null
  let pingTimer = null
  let reconnectCount = 0
  let reconnectTimer = null
  let currentUrl = ''
  let currentToken = ''
  let destroyed = false

  function connect(wsUrl, token) {
    if (destroyed) return
    currentUrl = wsUrl
    currentToken = token

    setStatus('connecting')
    reconnectCount = 0

    try {
      ws = new WebSocket(`${wsUrl}?token=${token}`)
      ws.binaryType = 'arraybuffer'

      ws.onopen = () => {
        setStatus('connected')
        reconnectCount = 0
        startPing()
      }

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          console.log('[WS] 收到语音数据:', event.data.byteLength, 'bytes')
          onAudioChunk(event.data)
        } else {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'pong') return // handled silently
            console.log('[WS] 收到消息:', msg.type, msg.data)
            onJsonMessage(msg)
          } catch {
            console.warn('[WS] 收到无法解析的消息:', event.data)
          }
        }
      }

      ws.onclose = (event) => {
        clearPing()
        if (destroyed) return
        // Auth failure — notify caller so they can refresh token
        if (event.code === 4001) {
          setStatus('disconnected')
          if (onAuthFailure) onAuthFailure()
          return
        }
        // Interview ended — redirect to report
        if (event.code === 4000) {
          setStatus('disconnected')
          if (onInterviewEnded) onInterviewEnded()
          return
        }
        // Normal closure or terminal codes — do not reconnect
        if (event.code === 1000 || event.code === 1001 || event.code >= 4000) {
          setStatus('disconnected')
          return
        }
        attemptReconnect()
      }

      ws.onerror = () => {
        // onclose will fire after onerror
      }
    } catch {
      attemptReconnect()
    }
  }

  function attemptReconnect() {
    if (destroyed || reconnectCount >= WS_RECONNECT_MAX) {
      setStatus('disconnected')
      return
    }
    setStatus('reconnecting')
    reconnectCount++
    const delay = WS_RECONNECT_INTERVALS[reconnectCount - 1] || 5000

    reconnectTimer = setTimeout(() => {
      if (!destroyed) {
        connect(currentUrl, currentToken)
      }
    }, delay)
  }

  function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      if (data instanceof ArrayBuffer || data instanceof Uint8Array) {
        ws.send(data)
      } else {
        console.log('[WS] 发送消息:', data.type, data.data)
        ws.send(JSON.stringify(data))
      }
    } else {
      console.warn('[WS] 发送失败(未连接):', data.type)
    }
  }

  function sendBinary(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  }

  function startPing() {
    clearPing()
    pingTimer = setInterval(() => {
      send({ type: 'ping' })
    }, 15000)
  }

  function clearPing() {
    if (pingTimer) {
      clearInterval(pingTimer)
      pingTimer = null
    }
  }

  function setStatus(status) {
    console.log('[WS] 连接状态:', status)
    wsStatus.value = status
    onStatusChange(status)
  }

  function disconnect() {
    destroyed = true
    clearPing()
    clearTimeout(reconnectTimer)
    if (ws) {
      ws.onclose = null // prevent reconnect
      ws.close(1000)
      ws = null
    }
    setStatus('disconnected')
  }

  onUnmounted(disconnect)

  return { wsStatus, connect, disconnect, send, sendBinary }
}
