"""Tests for Qwen TTS & ASR (通义千问 语音合成 / 语音识别) via DashScope SDK.

Usage:
    # 只跑单元测试（不需要网络）：
    pytest tests/test_qwen_tts.py -v -k "not api"

    # 跑全部测试（含 API）：
    TTS_OUTPUT_DIR=./output TTS_OVERWRITE=1 pytest tests/test_qwen_tts.py -v

    # 跳过 API 测试：
    TTS_SKIP_API=1 pytest tests/test_qwen_tts.py -v

    # CLI 模式：
    python tests/test_qwen_tts.py --text "你好世界" --overwrite
    python tests/test_qwen_tts.py --overwrite  # 跑默认测试套件
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

DEFAULT_TEXTS: list[str] = [
    "你好，欢迎参加本次AI模拟面试。",
    "请做一个简短的自我介绍，包括你的姓名、工作经验和技能特长。",
]

DEFAULT_MODEL = "qwen-tts"
DEFAULT_VOICE = "Cherry"
DEFAULT_SPEECH_RATE = 1.0
DEFAULT_VOLUME = 50
DEFAULT_PITCH_RATE = 1.0

WAV_SAMPLE_RATE = 16000
WAV_SAMPLE_WIDTH = 2
WAV_CHANNELS = 1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_dotenv_value(key: str) -> str:
    if not _ENV_FILE.exists():
        return ""
    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    except Exception:
        pass
    return ""


def save_pcm_as_wav(
    pcm_data: bytes,
    filepath: str | Path,
    overwrite: bool = False,
) -> bool:
    """Save raw PCM bytes as a WAV file (16kHz, 16-bit, mono)."""
    filepath = Path(filepath)

    if filepath.exists() and not overwrite:
        print(f"[SKIP] Output file already exists: {filepath}")
        print("       Use TTS_OVERWRITE=1 or --overwrite to replace it.")
        return False

    filepath.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(WAV_CHANNELS)
        wf.setsampwidth(WAV_SAMPLE_WIDTH)
        wf.setframerate(WAV_SAMPLE_RATE)
        wf.writeframes(pcm_data)

    duration = len(pcm_data) / (WAV_SAMPLE_RATE * WAV_SAMPLE_WIDTH * WAV_CHANNELS)
    file_size = filepath.stat().st_size
    print(f"[SAVED] {filepath}")
    print(f"        size={file_size:,} bytes  duration={duration:.2f}s  "
          f"sample_rate={WAV_SAMPLE_RATE}Hz  channels={WAV_CHANNELS}")
    return True


# ---------------------------------------------------------------------------
# Core: Qwen TTS synthesis via DashScope SDK (HTTP REST streaming)
# ---------------------------------------------------------------------------


def _get_sdk():
    """Lazy-load the DashScope SDK SpeechSynthesizer."""
    import dashscope
    from dashscope.audio.qwen_tts import SpeechSynthesizer
    return dashscope, SpeechSynthesizer


def _init_sdk_api_key(api_key: str) -> None:
    import dashscope
    dashscope.api_key = api_key


def qwen_tts_synthesize(
    text: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    speech_rate: float = DEFAULT_SPEECH_RATE,
    volume: int = DEFAULT_VOLUME,
    pitch_rate: float = DEFAULT_PITCH_RATE,
    sample_rate: int = WAV_SAMPLE_RATE,
    log: logging.Logger | None = None,
) -> bytes:
    """Synthesize text to PCM bytes via Qwen TTS HTTP REST API (streaming).

    Uses the DashScope SDK SpeechSynthesizer with stream=True,
    which returns audio as base64-encoded PCM chunks over HTTP SSE.
    No WebSocket required.
    """
    log = log or logging.getLogger(__name__)

    if not api_key:
        log.error("No DASHSCOPE_API_KEY provided")
        return b""
    if not text or not text.strip():
        log.warning("Empty text, skipping TTS")
        return b""

    try:
        _init_sdk_api_key(api_key)
        _, SpeechSynthesizer = _get_sdk()

        log.info(f"TTS HTTP REST: model={model} voice={voice} text_len={len(text)}")

        result = SpeechSynthesizer.call(
            model=model,
            text=text,
            voice=voice,
            format="pcm",
            sample_rate=sample_rate,
            rate=speech_rate,
            volume=volume,
            pitch=pitch_rate,
            stream=True,
        )

        audio_chunks: list[bytes] = []
        for rsp in result:
            output = rsp.output or {}
            data = output.get("audio", {}).get("data", "")
            if data:
                audio_chunks.append(base64.b64decode(data))

        if not audio_chunks:
            log.warning("No audio data received from TTS")
            return b""

        pcm = b"".join(audio_chunks)
        log.info(f"TTS complete: {len(pcm)} bytes ({len(audio_chunks)} chunks)")
        return pcm

    except Exception:
        log.exception("Qwen TTS failed")
        return b""


# ---------------------------------------------------------------------------
# pytest helpers
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    return os.environ.get("DASHSCOPE_API_KEY") or _load_dotenv_value("DASHSCOPE_API_KEY")


_api_key = _get_api_key()
_api_key_available = bool(_api_key)

_skip_api = not _api_key_available or bool(os.environ.get("TTS_SKIP_API"))
if not _api_key_available:
    _skip_api_reason = "DASHSCOPE_API_KEY not configured in .env or environment"
elif os.environ.get("TTS_SKIP_API"):
    _skip_api_reason = "TTS_SKIP_API=1 is set (network tests disabled)"
else:
    _skip_api_reason = ""

skip_api = pytest.mark.skipif(_skip_api, reason=_skip_api_reason)


def _tts_output_dir() -> str:
    return os.environ.get("TTS_OUTPUT_DIR", "./output")


def _tts_overwrite() -> bool:
    return bool(os.environ.get("TTS_OVERWRITE"))


# ---------------------------------------------------------------------------
# pytest test cases
# ---------------------------------------------------------------------------


class TestQwenTTSFileOutput:
    """Unit tests for WAV file saving — no API/network needed."""

    def test_save_wav_creates_valid_file(self, tmp_path):
        t = np.linspace(0, 1, 16000, endpoint=False)
        samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        pcm = samples.tobytes()

        filepath = tmp_path / "test_output.wav"
        assert save_pcm_as_wav(pcm, filepath)
        assert filepath.exists()

        with wave.open(str(filepath), "rb") as wf:
            assert wf.getnchannels() == WAV_CHANNELS
            assert wf.getsampwidth() == WAV_SAMPLE_WIDTH
            assert wf.getframerate() == WAV_SAMPLE_RATE
            assert wf.getnframes() == 16000

    def test_save_wav_skips_existing_without_overwrite(self, tmp_path):
        filepath = tmp_path / "existing.wav"
        filepath.write_bytes(b"dummy")
        assert not save_pcm_as_wav(b"\x00" * 320, filepath, overwrite=False)
        assert filepath.read_bytes() == b"dummy"

    def test_save_wav_overwrites_existing(self, tmp_path):
        filepath = tmp_path / "overwrite_me.wav"
        filepath.write_bytes(b"dummy")

        t = np.linspace(0, 0.1, 1600, endpoint=False)
        samples = (np.sin(2 * np.pi * 880 * t) * 8000).astype(np.int16)
        pcm = samples.tobytes()

        assert save_pcm_as_wav(pcm, filepath, overwrite=True)
        assert filepath.stat().st_size > 100


class TestQwenTTSSynthesizeNoNetwork:
    """Tests that don't need a real API connection."""

    def test_empty_text_returns_empty(self):
        assert qwen_tts_synthesize("", api_key="") == b""

    def test_no_api_key_returns_empty(self):
        assert qwen_tts_synthesize("你好", api_key="") == b""


@pytest.mark.api
class TestQwenTTSSynthesizeAPI:
    """Tests that call the real DashScope HTTP REST API."""

    @skip_api
    def test_synthesize_short_text(self):
        pcm = qwen_tts_synthesize("你好世界", api_key=_api_key)
        assert isinstance(pcm, bytes)
        assert len(pcm) > 0, (
            "No audio produced. Possible causes:\n"
            "  - Invalid API key (check .env DASHSCOPE_API_KEY)\n"
            "  - Network cannot reach dashscope.aliyuncs.com"
        )

    @skip_api
    def test_synthesize_longer_text(self):
        text = "你好，欢迎参加本次AI模拟面试。请做一个简短的自我介绍。"
        pcm = qwen_tts_synthesize(text, api_key=_api_key)
        assert len(pcm) > 0

    @skip_api
    def test_synthesize_and_save_wav(self):
        text = "我对Python和FastAPI开发非常熟悉，平时使用Docker部署项目。"
        pcm = qwen_tts_synthesize(text, api_key=_api_key)
        assert len(pcm) > 0

        filepath = Path(_tts_output_dir()) / "qwen_tts_api_test.wav"
        assert save_pcm_as_wav(pcm, filepath, overwrite=_tts_overwrite()), (
            f"Failed to save {filepath} — set TTS_OVERWRITE=1 to replace existing file"
        )


@pytest.mark.api
class TestQwenTTSVoiceParametersAPI:
    """Voice parameter variation tests (requires API)."""

    @skip_api
    def test_fast_speech_rate(self):
        out_dir = _tts_output_dir()
        overwrite = _tts_overwrite()

        pcm = qwen_tts_synthesize(
            "语速测试文本快速朗读", api_key=_api_key, speech_rate=1.5,
        )
        assert len(pcm) > 0
        save_pcm_as_wav(pcm, Path(out_dir) / "qwen_tts_fast.wav", overwrite=overwrite)

    @skip_api
    def test_loud_volume(self):
        out_dir = _tts_output_dir()
        overwrite = _tts_overwrite()

        pcm = qwen_tts_synthesize(
            "音量测试文本大声朗读", api_key=_api_key, volume=80,
        )
        assert len(pcm) > 0
        save_pcm_as_wav(pcm, Path(out_dir) / "qwen_tts_loud.wav", overwrite=overwrite)


# ---------------------------------------------------------------------------
# Core: Qwen ASR transcription via DashScope SDK
# ---------------------------------------------------------------------------

ASR_MODEL = "qwen3-asr-flash-realtime"


async def qwen_asr_transcribe(
    audio_bytes: bytes,
    *,
    api_key: str,
    model: str = ASR_MODEL,
    sample_rate: int = WAV_SAMPLE_RATE,
    timeout: float = 30.0,
    log: logging.Logger | None = None,
) -> str:
    """Transcribe PCM audio bytes to text via DashScope SDK Recognition.

    Saves PCM to a temp WAV file, calls Recognition.call() in thread pool
    (SDK manages WebSocket internally), and extracts the recognized text.
    Returns empty string on failure or timeout.
    """
    log = log or logging.getLogger(__name__)

    if not api_key:
        log.error("No DASHSCOPE_API_KEY provided")
        return ""
    if not audio_bytes or len(audio_bytes) < 1600:
        log.warning("Audio too short, skipping ASR")
        return ""

    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="qwen_asr_test_")
    os.close(fd)
    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(WAV_CHANNELS)
            wf.setsampwidth(WAV_SAMPLE_WIDTH)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_bytes)

        def _call():
            import dashscope
            from dashscope.audio.asr import Recognition

            dashscope.api_key = api_key
            rec = Recognition(
                model=model,
                callback=None,
                format="pcm",
                sample_rate=sample_rate,
            )
            result = rec.call(wav_path)
            sentences = result.get_sentence()
            if sentences is None:
                return ""
            if isinstance(sentences, dict):
                return sentences.get("text", "")
            elif isinstance(sentences, list):
                return "".join(s.get("text", "") for s in sentences)
            return ""

        text = await asyncio.wait_for(
            asyncio.to_thread(_call),
            timeout=timeout,
        )
        log.info(f"ASR complete: text_length={len(text)}")
        return text

    except asyncio.TimeoutError:
        log.error(f"ASR timed out after {timeout}s")
        return ""
    except Exception:
        log.exception("Qwen ASR failed")
        return ""
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


@pytest.mark.api
class TestQwenASRNoNetwork:
    """ASR tests that don't need a real API connection."""

    @pytest.mark.asyncio
    async def test_empty_audio_returns_empty(self):
        assert await qwen_asr_transcribe(b"", api_key="") == ""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_empty(self):
        t = np.linspace(0, 0.2, 3200, endpoint=False)
        pcm = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).tobytes()
        assert await qwen_asr_transcribe(pcm, api_key="") == ""


@pytest.mark.api
class TestQwenASRAPI:
    """ASR tests that call the real DashScope API (requires valid key + network)."""

    @pytest.mark.asyncio
    @skip_api
    async def test_transcribe_sine_wave_returns_empty_or_gibberish(self):
        """A short sine wave has no speech — ASR should return empty or nonsense."""
        t = np.linspace(0, 1, 16000, endpoint=False)
        pcm = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16).tobytes()
        text = await qwen_asr_transcribe(pcm, api_key=_api_key)
        assert isinstance(text, str)

    @pytest.mark.asyncio
    @skip_api
    async def test_transcribe_too_short_audio_returns_empty(self):
        """Extremely short audio (< 100ms) should be rejected gracefully."""
        pcm = b"\x00" * 800  # 50ms at 16kHz 16bit
        text = await qwen_asr_transcribe(pcm, api_key=_api_key)
        assert text == ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _run_test_suite(output_dir: str, overwrite: bool) -> int:
    log = logging.getLogger("qwen_tts_cli")
    api_key = _get_api_key()
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY not configured")
        return 1

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    passed = 0

    for i, text in enumerate(DEFAULT_TEXTS):
        filename = f"qwen_tts_{i:02d}.wav"
        filepath = out / filename
        print(f"\n{'=' * 60}")
        print(f"Test {i + 1}/{len(DEFAULT_TEXTS)}")
        print(f"Text: {text}")

        start = time.perf_counter()
        pcm = qwen_tts_synthesize(text, api_key=api_key, log=log)
        elapsed = time.perf_counter() - start

        if pcm:
            if save_pcm_as_wav(pcm, filepath, overwrite=overwrite):
                passed += 1
            print(f"[OK] {len(pcm):,} PCM bytes in {elapsed:.2f}s")
        else:
            print(f"[FAIL] No audio (took {elapsed:.2f}s)")

    print(f"\n{'=' * 60}")
    print(f"Summary: {passed}/{len(DEFAULT_TEXTS)} files saved")
    return 0 if passed == len(DEFAULT_TEXTS) else 1


def _run_single(text: str, output_path: str, overwrite: bool) -> int:
    log = logging.getLogger("qwen_tts_cli")
    api_key = _get_api_key()
    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY not configured")
        return 1

    print(f"Text: {text}")
    print(f"Output: {output_path}")

    start = time.perf_counter()
    pcm = qwen_tts_synthesize(text, api_key=api_key, log=log)
    elapsed = time.perf_counter() - start

    if not pcm:
        print(f"[FAIL] No audio (took {elapsed:.2f}s)")
        return 1

    if save_pcm_as_wav(pcm, output_path, overwrite=overwrite):
        print(f"[OK] {len(pcm):,} PCM bytes in {elapsed:.2f}s")
        return 0
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Test Qwen TTS (通义千问 文字转语音) via DashScope HTTP REST",
    )
    parser.add_argument("--text", help="Single text to synthesize")
    parser.add_argument("--output", default="./output/tts_result.wav",
                        help="Output WAV path (used with --text)")
    parser.add_argument("--output-dir", default="./output",
                        help="Output directory for test suite")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable DEBUG logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.text:
        exit_code = _run_single(args.text, args.output, args.overwrite)
    else:
        exit_code = _run_test_suite(args.output_dir, args.overwrite)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
