import { ref, onUnmounted } from 'vue'
import { float32ToPCM16, vadEnergy } from '../utils/audioUtils.js'

/**
 * Microphone capture + VAD-based interrupt detection.
 * Supports Silero VAD (preferred) with energy VAD fallback.
 *
 * @param {object} options
 * @param {function} options.onAudioChunk - receives ArrayBuffer (PCM16) to send via WS
 * @param {function} options.onSpeechStart - VAD detects speech start → send interrupt
 * @param {function} options.onSpeechEnd - VAD detects speech end
 * @param {function} options.externalVAD - optional Silero VAD detect function
 * @param {number} options.vadThreshold - RMS energy threshold (default 0.01)
 * @param {number} options.sampleRate - target sample rate (default 16000)
 * @param {number} options.chunkDuration - audio chunk duration in ms (default 100)
 */
export function useAudioRecorder(options = {}) {
  const {
    onAudioChunk = () => {},
    onSpeechStart = () => {},
    onSpeechEnd = () => {},
    externalVAD = null,
    vadThreshold = 0.01,
    sampleRate = 16000,
    chunkDuration = 100
  } = options

  const isRecording = ref(false)
  const isSpeaking = ref(false)
  const isInitialized = ref(false)

  let audioContext = null
  let stream = null
  let source = null
  let workletNode = null
  let scriptNode = null
  let pcmBuffer = new Float32Array(0)
  const samplesPerChunk = Math.floor(sampleRate * chunkDuration / 1000)
  let speechHangover = 0
  const hangoverFrames = 25 // ~2.5s of silence before speech end

  async function init() {
    if (isInitialized.value) return true
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true
        }
      })

      audioContext = new AudioContext({ sampleRate })

      // Use AudioWorklet if supported, fallback to ScriptProcessorNode
      if (audioContext.audioWorklet) {
        try {
          await audioContext.audioWorklet.addModule(createWorkletBlob())
          source = audioContext.createMediaStreamSource(stream)
          workletNode = new AudioWorkletNode(audioContext, 'pcm-processor')
          workletNode.port.onmessage = (event) => {
            processAudioChunk(event.data)
          }
          source.connect(workletNode)
          isInitialized.value = true
          return true
        } catch {
          // Fallback to ScriptProcessor
        }
      }

      // Fallback: ScriptProcessorNode
      source = audioContext.createMediaStreamSource(stream)
      scriptNode = audioContext.createScriptProcessor(4096, 1, 1)
      scriptNode.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0)
        processAudioChunk(new Float32Array(input))
      }
      source.connect(scriptNode)
      scriptNode.connect(audioContext.destination)

      isInitialized.value = true
      return true
    } catch (err) {
      console.error('Microphone init failed:', err)
      return false
    }
  }

  function processAudioChunk(samples) {
    if (!isRecording.value) return

    // Append to buffer
    const newBuffer = new Float32Array(pcmBuffer.length + samples.length)
    newBuffer.set(pcmBuffer)
    newBuffer.set(samples, pcmBuffer.length)
    pcmBuffer = newBuffer

    // Send chunks
    while (pcmBuffer.length >= samplesPerChunk) {
      const chunk = pcmBuffer.slice(0, samplesPerChunk)
      pcmBuffer = pcmBuffer.slice(samplesPerChunk)

      const pcm16 = float32ToPCM16(chunk)
      onAudioChunk(pcm16)

      // VAD detection — prefer Silero VAD, fallback to energy VAD
      let handled = false
      if (externalVAD) {
        const result = externalVAD(chunk)
        if (result && result.event === 'start') {
          isSpeaking.value = true
          speechHangover = hangoverFrames
          onSpeechStart()
          handled = true
        } else if (result && result.event === 'end') {
          isSpeaking.value = false
          speechHangover = 0
          onSpeechEnd()
          handled = true
        } else if (result) {
          // VAD is tracking but no event — update speaking state
          isSpeaking.value = result.speaking
          if (result.speaking) speechHangover = hangoverFrames
          handled = true
        }
      }

      // Fallback to energy VAD when externalVAD not available or returned null
      if (!handled) {
        const voiceDetected = vadEnergy(chunk, vadThreshold)
        if (voiceDetected) {
          speechHangover = hangoverFrames
          if (!isSpeaking.value) {
            isSpeaking.value = true
            onSpeechStart()
          }
        } else if (isSpeaking.value) {
          speechHangover--
          if (speechHangover <= 0) {
            isSpeaking.value = false
            onSpeechEnd()
          }
        }
      }
    }
  }

  function start() {
    if (!isInitialized.value || !audioContext) return
    if (audioContext.state === 'suspended') {
      audioContext.resume()
    }
    isRecording.value = true
    isSpeaking.value = false
    speechHangover = 0
    pcmBuffer = new Float32Array(0)
  }

  function stop() {
    isRecording.value = false
    isSpeaking.value = false
    pcmBuffer = new Float32Array(0)
  }

  function destroy() {
    stop()
    if (workletNode) {
      workletNode.disconnect()
      workletNode = null
    }
    if (scriptNode) {
      scriptNode.disconnect()
      scriptNode = null
    }
    if (source) {
      source.disconnect()
      source = null
    }
    if (stream) {
      stream.getTracks().forEach(t => t.stop())
      stream = null
    }
    if (audioContext) {
      audioContext.close()
      audioContext = null
    }
    isInitialized.value = false
  }

  onUnmounted(destroy)

  return { isRecording, isSpeaking, isInitialized, init, start, stop, destroy }
}

// AudioWorklet processor as a Blob URL (inline to avoid separate file)
function createWorkletBlob() {
  const code = `
    class PCMProcessor extends AudioWorkletProcessor {
      process(inputs) {
        const input = inputs[0];
        if (input && input.length > 0) {
          const channel = input[0];
          this.port.postMessage(channel.slice(0));
        }
        return true;
      }
    }
    registerProcessor('pcm-processor', PCMProcessor);
  `
  return URL.createObjectURL(new Blob([code], { type: 'application/javascript' }))
}
