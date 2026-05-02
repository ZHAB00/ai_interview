"""Tests for AudioHandler and STT/TTS providers."""

import io
import os
import wave

import pytest

from app.ws.audio_handler import (
    AUDIO_CHANNELS,
    AUDIO_SAMPLE_RATE,
    AUDIO_SAMPLE_WIDTH,
    AliyunSTTProvider,
    AliyunTTSProvider,
    AudioHandler,
    BaseSTTProvider,
    BaseTTSProvider,
)


class MockSTTProvider(BaseSTTProvider):
    """Mock STT provider for testing."""
    async def transcribe(self, audio_bytes, sample_rate=16000):
        if not audio_bytes:
            return ""
        return "这是转写结果"


class MockTTSProvider(BaseTTSProvider):
    """Mock TTS provider for testing."""
    async def synthesize(self, text):
        if not text:
            return b""
        # Generate minimal WAV bytes
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 160)  # 10ms silent
        return buf.getvalue()


class TestSTTProvider:
    @pytest.mark.asyncio
    async def test_aliyun_stt_without_appkey(self, monkeypatch):
        """AliyunSTT returns empty string when no appkey configured."""
        monkeypatch.setattr("app.ws.audio_handler.settings.ALIYUN_NLS_APPKEY", "")
        provider = AliyunSTTProvider(appkey="")
        result = await provider.transcribe(b"audio data")
        assert result == ""

    @pytest.mark.asyncio
    async def test_mock_stt(self):
        """Mock STT returns transcribed text."""
        provider = MockSTTProvider()
        result = await provider.transcribe(b"some audio")
        assert result == "这是转写结果"

    @pytest.mark.asyncio
    async def test_mock_stt_empty_audio(self):
        """Empty audio returns empty string."""
        provider = MockSTTProvider()
        result = await provider.transcribe(b"")
        assert result == ""


class TestTTSProvider:
    @pytest.mark.asyncio
    async def test_aliyun_tts_without_appkey(self, monkeypatch):
        """AliyunTTS returns empty bytes when no appkey configured."""
        monkeypatch.setattr("app.ws.audio_handler.settings.ALIYUN_NLS_APPKEY", "")
        provider = AliyunTTSProvider(appkey="")
        result = await provider.synthesize("你好")
        assert result == b""

    @pytest.mark.asyncio
    async def test_mock_tts(self):
        """Mock TTS returns audio bytes."""
        provider = MockTTSProvider()
        result = await provider.synthesize("测试文本")
        assert len(result) > 0
        # Should be valid WAV with correct params
        buf = io.BytesIO(result)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000


class TestAudioHandler:
    @pytest.mark.asyncio
    async def test_speech_to_text(self):
        """AudioHandler delegates to STT provider."""
        handler = AudioHandler.__new__(AudioHandler)
        handler.stt = MockSTTProvider()
        result = await handler.speech_to_text(b"test audio")
        assert result == "这是转写结果"

    @pytest.mark.asyncio
    async def test_text_to_speech(self):
        """AudioHandler delegates to TTS provider."""
        handler = AudioHandler.__new__(AudioHandler)
        handler.tts = MockTTSProvider()
        result = await handler.text_to_speech("hello")
        assert len(result) > 0

    def test_append_chunk(self, tmp_path):
        """Appending audio chunks writes to temp file."""
        handler = AudioHandler.__new__(AudioHandler)
        handler._chunk_files = {}
        handler._utterance_buffers = {}

        handler.append_chunk(999, b"chunk1")
        handler.append_chunk(999, b"chunk2")

        assert 999 in handler._chunk_files
        path = handler._chunk_files[999]
        with open(path, "rb") as f:
            data = f.read()
        assert data == b"chunk1chunk2"

        # Cleanup
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_merge_empty(self):
        """Merging with no chunks returns empty string."""
        handler = AudioHandler.__new__(AudioHandler)
        handler._chunk_files = {}
        url = await handler.merge_and_upload(999)
        assert url == ""

    @pytest.mark.asyncio
    async def test_start_end_interview(self, monkeypatch):
        """Start and end interview recording lifecycle."""
        import tempfile

        with monkeypatch.context() as m:
            tmp = tempfile.mkdtemp()
            m.setattr("app.core.config.settings.UPLOAD_DIR", tmp)

            handler = AudioHandler.__new__(AudioHandler)
            handler.stt = MockSTTProvider()
            handler.tts = MockTTSProvider()
            handler._chunk_files = {}
            handler._utterance_buffers = {}

            await handler.start_interview(123)
            handler.append_chunk(123, b"hello" * 1000)

            url = await handler.end_interview(123)
            # URL should be non-empty (local fallback)
            assert len(url) > 0
            assert url.startswith("/uploads/audio/") or "uploads" in url
