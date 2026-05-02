import { ref, computed } from 'vue'

/**
 * Silero VAD via onnxruntime-web.
 * Detects speech segments from Float32Array audio chunks.
 *
 * @param {object} options
 * @param {number} options.sampleRate - audio sample rate (default 16000)
 * @param {number} options.sensitivity - 0-1, higher = more sensitive (default 0.5)
 * @param {number} options.silenceFrames - frames of silence before speech end (default 8)
 */
export function useSileroVAD(options = {}) {
  const {
    sampleRate = 16000,
    sensitivity = 0.5,
    silenceFrames = 8
  } = options

  const isReady = ref(false)
  const isSpeaking = ref(false)
  const sensitivityLevel = ref(sensitivity)

  let ortSession = null
  let ort = null
  let h = null
  let c = null
  let sr = null
  let silenceCount = 0
  // Map sensitivity (0.1-0.9) to threshold (0.66-0.34): higher sensitivity → lower threshold → detects quieter speech
  const speechThreshold = computed(() => 0.7 - sensitivityLevel.value * 0.4)

  async function init() {
    try {
      ort = await import('onnxruntime-web')

      // Silero VAD ONNX model — load from GitHub via jsdelivr CDN
      const modelUrl = 'https://cdn.jsdelivr.net/gh/snakers4/silero-vad@master/models/silero_vad.onnx'
      ortSession = await ort.InferenceSession.create(modelUrl)

      // Initialize state tensors
      const batchSize = 1
      const stateSize = 2 * 1 * 128 // (2*1*128)

      sr = new ort.Tensor(
        'int64',
        new BigInt64Array([BigInt(sampleRate)]),
        [1]
      )

      h = new ort.Tensor(
        'float32',
        new Float32Array(stateSize),
        [2, batchSize, 128]
      )

      c = new ort.Tensor(
        'float32',
        new Float32Array(stateSize),
        [2, batchSize, 128]
      )

      isReady.value = true
      return true
    } catch (err) {
      console.warn('Silero VAD init failed, falling back to energy VAD:', err.message)
      return false
    }
  }

  /**
   * Run VAD inference on audio chunk.
   * @param {Float32Array} samples - audio samples normalized [-1, 1] at 16kHz
   * @returns {object} { speaking: boolean, prob: number }
   */
  function detect(samples) {
    if (!isReady.value || !ortSession) {
      return null // caller should fall back to energy VAD
    }

    try {
      const feed = {
        input: new ort.Tensor('float32', samples, [1, samples.length]),
        sr,
        h,
        c
      }

      const results = ortSession.run(feed)
      const output = results.output.data[0] // speech probability
      h = results.hn
      c = results.cn

      const speaking = output > speechThreshold.value
      if (speaking) {
        silenceCount = 0
        if (!isSpeaking.value) {
          isSpeaking.value = true
          return { speaking: true, prob: output, event: 'start' }
        }
      } else if (isSpeaking.value) {
        silenceCount++
        if (silenceCount >= silenceFrames) {
          isSpeaking.value = false
          return { speaking: false, prob: output, event: 'end' }
        }
      }

      return { speaking: isSpeaking.value, prob: output, event: null }
    } catch {
      return null
    }
  }

  function reset() {
    silenceCount = 0
    isSpeaking.value = false
    // Re-init state tensors
    const stateSize = 2 * 1 * 128
    h = new ort.Tensor('float32', new Float32Array(stateSize), [2, 1, 128])
    c = new ort.Tensor('float32', new Float32Array(stateSize), [2, 1, 128])
  }

  function setSensitivity(val) {
    sensitivityLevel.value = val
    silenceCount = 0
  }

  function destroy() {
    ortSession = null
    ort = null
    h = null
    c = null
    sr = null
    isReady.value = false
  }

  return { isReady, isSpeaking, sensitivityLevel, init, detect, reset, setSensitivity, destroy }
}
