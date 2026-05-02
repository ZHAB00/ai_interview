/**
 * Convert Float32 PCM samples to 16-bit PCM ArrayBuffer for WebSocket transmission.
 * @param {Float32Array} samples - normalized float samples [-1, 1]
 * @returns {ArrayBuffer} 16-bit PCM
 */
export function float32ToPCM16(samples) {
  const buf = new ArrayBuffer(samples.length * 2)
  const view = new DataView(buf)
  for (let i = 0; i < samples.length; i++) {
    let s = Math.max(-1, Math.min(1, samples[i]))
    s = s < 0 ? s * 0x8000 : s * 0x7FFF
    view.setInt16(i * 2, s, true)
  }
  return buf
}

/**
 * Convert base64 string to Float32Array for playback.
 * @param {string} base64
 * @returns {Float32Array}
 */
export function base64ToFloat32(base64) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i)
  }
  const int16 = new Int16Array(bytes.buffer)
  const float32 = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768
  }
  return float32
}

/**
 * Append a PCM16 ArrayBuffer to a float audio buffer.
 * @param {Float32Array} dest - destination buffer
 * @param {number} destOffset - write offset in dest
 * @param {ArrayBuffer} src - source PCM16 data
 * @returns {number} number of samples written
 */
export function appendPCM16ToBuffer(dest, destOffset, src) {
  const int16 = new Int16Array(src)
  for (let i = 0; i < int16.length; i++) {
    dest[destOffset + i] = int16[i] / 32768
  }
  return int16.length
}

/**
 * Convert PCM16 ArrayBuffer to Float32Array for Web Audio API playback.
 * @param {ArrayBuffer|Uint8Array} pcm16 - 16-bit PCM audio data
 * @returns {Float32Array} normalized float samples [-1, 1]
 */
export function pcm16ToFloat32(pcm16) {
  const bytes = pcm16 instanceof Uint8Array ? pcm16 : new Uint8Array(pcm16)
  const int16 = new Int16Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.length / 2))
  const float32 = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768
  }
  return float32
}

/**
 * Convert PCM16 ArrayBuffer to a WAV file (ArrayBuffer) with proper RIFF header.
 * This lets us use the <audio> element for reliable playback instead of AudioContext.
 * @param {ArrayBuffer|Uint8Array} pcm16 - raw PCM16 audio data
 * @param {number} sampleRate - sample rate in Hz (default 24000 for DashScope TTS)
 * @param {number} numChannels - number of channels (default 1)
 * @returns {ArrayBuffer} complete WAV file
 */
export function pcm16ToWav(pcm16, sampleRate = 24000, numChannels = 1) {
  const bytes = pcm16 instanceof Uint8Array ? pcm16 : new Uint8Array(pcm16)
  const dataLen = bytes.length - (bytes.length % 2)  // ensure even
  const headerLen = 44
  const totalLen = headerLen + dataLen
  const buf = new ArrayBuffer(totalLen)
  const view = new DataView(buf)

  // RIFF header
  writeString(view, 0, 'RIFF')
  view.setUint32(4, totalLen - 8, true)
  writeString(view, 8, 'WAVE')

  // fmt chunk
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true)           // chunk size
  view.setUint16(20, 1, true)            // PCM format
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * numChannels * 2, true)  // byte rate
  view.setUint16(32, numChannels * 2, true)   // block align
  view.setUint16(34, 16, true)           // bits per sample

  // data chunk
  writeString(view, 36, 'data')
  view.setUint32(40, dataLen, true)

  // Copy PCM data
  const out = new Uint8Array(buf)
  out.set(bytes.subarray(0, dataLen), headerLen)
  return buf
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

/**
 * Simple VAD — energy-based threshold. Returns true when speech is detected.
 * @param {Float32Array} samples
 * @param {number} threshold - RMS threshold, default 0.01
 * @returns {boolean}
 */
export function vadEnergy(samples, threshold = 0.01) {
  let sum = 0
  for (let i = 0; i < samples.length; i++) {
    sum += samples[i] * samples[i]
  }
  const rms = Math.sqrt(sum / samples.length)
  return rms > threshold
}
