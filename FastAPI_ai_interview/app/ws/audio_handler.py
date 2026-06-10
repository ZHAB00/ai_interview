"""Audio handler - STT/TTS abstraction with provider implementations.

Responsibilities:
- speech_to_text(audio_bytes) -> str: forward to cloud STT, return recognized text
- text_to_speech(text) -> bytes: call cloud TTS, return audio bytes
- append_chunk(interview_id, audio_bytes): append audio frame to temp file
- merge_and_upload(interview_id) -> str: merge temp file to WAV, upload, return URL
"""

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import shutil
import os
import tempfile
import time
import urllib.parse
import uuid
import wave
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.security import create_file_token

logger = logging.getLogger(__name__)

# PCM 16kHz 16bit mono
AUDIO_SAMPLE_RATE = 16000
AUDIO_SAMPLE_WIDTH = 2  # 16-bit
AUDIO_CHANNELS = 1


# ===== Alibaba Cloud NLS Token Manager =====

class AliyunTokenManager:
    """Fetches and caches Alibaba Cloud NLS auth token.

    Uses AccessKey ID + Secret to request a token from NLS meta endpoint.
    Tokens are cached in-memory with a 5-minute buffer before expiry.
    """

    META_ENDPOINT = "https://nls-meta.cn-shanghai.aliyuncs.com/"

    def __init__(self, access_key_id: str, access_key_secret: str):
        self._ak_id = access_key_id
        self._ak_secret = access_key_secret
        self._token: str | None = None
        self._expire_at: float = 0
        self._lock = asyncio.Lock()

    @staticmethod
    def _percent_encode(s: str) -> str:
        """Percent-encode per Alibaba Cloud API spec.

        Characters NOT encoded: A-Z a-z 0-9 - _ . ~
        """
        return urllib.parse.quote(str(s), safe="-_.~")

    @staticmethod
    def _sign(secret: str, string_to_sign: str) -> str:
        key = (secret + "&").encode("utf-8")
        raw_sig = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(raw_sig).decode("utf-8")

    async def get_token(self) -> str | None:
        """Return a valid token, refreshing from API when expired or missing."""
        # Cache hit: still valid with 5min buffer
        if self._token and time.time() < self._expire_at - 300:
            return self._token

        async with self._lock:
            if self._token and time.time() < self._expire_at - 300:
                return self._token

            params = {
                "AccessKeyId": self._ak_id,
                "Action": "CreateToken",
                "Format": "JSON",
                "RegionId": "cn-shanghai",
                "SignatureMethod": "HMAC-SHA1",
                "SignatureNonce": str(uuid.uuid4()),
                "SignatureVersion": "1.0",
                "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "Version": "2019-02-28",
            }

            sorted_keys = sorted(params.keys())
            canonical_qs = "&".join(
                f"{self._percent_encode(k)}={self._percent_encode(params[k])}"
                for k in sorted_keys
            )
            string_to_sign = (
                f"GET&{self._percent_encode('/')}&{self._percent_encode(canonical_qs)}"
            )
            signature = self._sign(self._ak_secret, string_to_sign)

            url = (
                f"{self.META_ENDPOINT}?{canonical_qs}"
                f"&Signature={self._percent_encode(signature)}"
            )

            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                self._token = data["Token"]["Id"]
                self._expire_at = data["Token"]["ExpireTime"]
                logger.info(f"NLS Token acquired, expires at {self._expire_at}")
                return self._token
            except Exception as e:
                logger.error(f"NLS Token request failed: {e}")
                return None


# Singleton token managers (lazy init)
_token_manager: AliyunTokenManager | None = None


def _get_token_manager() -> AliyunTokenManager | None:
    global _token_manager
    if _token_manager is None:
        if settings.ALIYUN_ACCESS_KEY_ID and settings.ALIYUN_ACCESS_KEY_SECRET:
            _token_manager = AliyunTokenManager(
                settings.ALIYUN_ACCESS_KEY_ID,
                settings.ALIYUN_ACCESS_KEY_SECRET,
            )
        else:
            return None
    return _token_manager


# ===== Provider Interfaces =====


class BaseSTTProvider(ABC):
    """Abstract STT (Speech-to-Text) provider."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """Convert speech audio bytes to text."""
        ...


class BaseTTSProvider(ABC):
    """Abstract TTS (Text-to-Speech) provider."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Convert text to speech audio bytes."""
        ...


# ===== Aliyun Providers =====


class AliyunSTTProvider(BaseSTTProvider):
    """Aliyun (Alibaba Cloud) Speech Recognition provider.

    Authenticates via NLS token (from AccessKey) + Appkey.
    """

    GATEWAY = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/asr"

    def __init__(self, appkey: str = ""):
        self.appkey = appkey or settings.ALIYUN_NLS_APPKEY

    # Alibaba Cloud real-time ASR has a 60s limit at 16kHz 16bit mono (~1.92 MB)
    MAX_STT_BYTES = 60 * 16000 * 2

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not self.appkey:
            logger.warning("ALIYUN_NLS_APPKEY not configured, returning empty text")
            return ""

        if not audio_bytes:
            return ""

        if len(audio_bytes) < 1600:
            logger.warning(f"STT audio too short: {len(audio_bytes)} bytes, skipping")
            return ""

        if len(audio_bytes) > self.MAX_STT_BYTES:
            logger.warning(
                f"STT audio too long: {len(audio_bytes)} bytes "
                f"(max {self.MAX_STT_BYTES}), truncating"
            )
            audio_bytes = audio_bytes[:self.MAX_STT_BYTES]

        token_mgr = _get_token_manager()
        if token_mgr is None:
            logger.warning("Alibaba Cloud AccessKey not configured, returning empty text")
            return ""

        token = await token_mgr.get_token()
        if not token:
            return ""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.GATEWAY,
                    params={
                        "appkey": self.appkey,
                        "format": "pcm",
                        "sample_rate": str(sample_rate),
                    },
                    content=audio_bytes,
                    headers={
                        "X-NLS-Token": token,
                        "Content-Type": "application/octet-stream",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("result", "")
                logger.info(f"STT completed: text_length={len(text)}")
                return text
        except Exception as e:
            logger.error(f"STT failed: {e}")
            return ""


class AliyunTTSProvider(BaseTTSProvider):
    """Aliyun (Alibaba Cloud) Text-to-Speech provider.

    Authenticates via NLS token (from AccessKey) + Appkey.
    """

    GATEWAY = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/tts"

    def __init__(self, appkey: str = ""):
        self.appkey = appkey or settings.ALIYUN_NLS_APPKEY

    async def synthesize(self, text: str) -> bytes:
        if not self.appkey:
            logger.warning("ALIYUN_NLS_APPKEY not configured, returning empty audio")
            return b""

        token_mgr = _get_token_manager()
        if token_mgr is None:
            logger.warning("Alibaba Cloud AccessKey not configured, returning empty audio")
            return b""

        token = await token_mgr.get_token()
        if not token:
            return b""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self.GATEWAY,
                    params={
                        "appkey": self.appkey,
                        "text": text,
                        "format": "pcm",
                        "sample_rate": "16000",
                        "voice": "aixia",
                    },
                    headers={
                        "X-NLS-Token": token,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                resp.raise_for_status()
                audio = resp.content
                logger.info(f"TTS completed: audio_bytes={len(audio)}")
                return audio
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return b""


# ===== DashScope / Qwen Providers =====

# Hot words for AI/tech interview ASR — improves recognition of technical terms.
# Weights 1-5, default 4. Higher = stronger bias (but too high may hurt others).
# See: https://www.alibabacloud.com/help/en/model-studio/custom-hot-words
ASR_HOTWORDS: list[dict] = [
    # AI / ML core
    {"text": "agent", "weight": 4, "lang": "en"},
    {"text": "LLM", "weight": 5, "lang": "en"},
    {"text": "RAG", "weight": 5, "lang": "en"},
    {"text": "prompt", "weight": 4, "lang": "en"},
    {"text": "embedding", "weight": 4, "lang": "en"},
    {"text": "transformer", "weight": 4, "lang": "en"},
    {"text": "GPT", "weight": 5, "lang": "en"},
    {"text": "fine-tuning", "weight": 4, "lang": "en"},
    {"text": "RLHF", "weight": 4, "lang": "en"},
    {"text": "inference", "weight": 3, "lang": "en"},
    {"text": "token", "weight": 3, "lang": "en"},
    {"text": "attention", "weight": 3, "lang": "en"},
    {"text": "BERT", "weight": 4, "lang": "en"},
    {"text": "diffusion", "weight": 4, "lang": "en"},
    {"text": "LoRA", "weight": 5, "lang": "en"},
    {"text": "encoder", "weight": 3, "lang": "en"},
    {"text": "decoder", "weight": 3, "lang": "en"},
    {"text": "checkpoint", "weight": 3, "lang": "en"},
    {"text": "dropout", "weight": 3, "lang": "en"},
    {"text": "softmax", "weight": 4, "lang": "en"},
    # Frameworks / tools
    {"text": "PyTorch", "weight": 5, "lang": "en"},
    {"text": "TensorFlow", "weight": 5, "lang": "en"},
    {"text": "CUDA", "weight": 5, "lang": "en"},
    {"text": "GPU", "weight": 5, "lang": "en"},
    {"text": "API", "weight": 5, "lang": "en"},
    {"text": "SDK", "weight": 5, "lang": "en"},
    {"text": "REST", "weight": 4, "lang": "en"},
    {"text": "gRPC", "weight": 4, "lang": "en"},
    {"text": "DevOps", "weight": 4, "lang": "en"},
    {"text": "CI/CD", "weight": 4, "lang": "en"},
    {"text": "Kubernetes", "weight": 5, "lang": "en"},
    {"text": "Docker", "weight": 5, "lang": "en"},
    {"text": "Node.js", "weight": 4, "lang": "en"},
    {"text": "React", "weight": 5, "lang": "en"},
    {"text": "Vue", "weight": 5, "lang": "en"},
    {"text": "Redis", "weight": 5, "lang": "en"},
    {"text": "Kafka", "weight": 5, "lang": "en"},
    {"text": "SQL", "weight": 5, "lang": "en"},
    {"text": "NoSQL", "weight": 4, "lang": "en"},
    {"text": "MySQL", "weight": 5, "lang": "en"},
    {"text": "PostgreSQL", "weight": 4, "lang": "en"},
    {"text": "MongoDB", "weight": 5, "lang": "en"},
    {"text": "nginx", "weight": 4, "lang": "en"},
    {"text": "Linux", "weight": 5, "lang": "en"},
    {"text": "Git", "weight": 5, "lang": "en"},
    {"text": "GitHub", "weight": 5, "lang": "en"},
    {"text": "JSON", "weight": 5, "lang": "en"},
    {"text": "YAML", "weight": 4, "lang": "en"},
    {"text": "WebSocket", "weight": 5, "lang": "en"},
    {"text": "HTTP", "weight": 5, "lang": "en"},
    {"text": "TCP", "weight": 4, "lang": "en"},
    # ML / DL
    {"text": "backpropagation", "weight": 3, "lang": "en"},
    {"text": "gradient", "weight": 3, "lang": "en"},
    {"text": "SGD", "weight": 4, "lang": "en"},
    {"text": "AdamW", "weight": 4, "lang": "en"},
    {"text": "ReLU", "weight": 4, "lang": "en"},
    {"text": "CNN", "weight": 4, "lang": "en"},
    {"text": "RNN", "weight": 4, "lang": "en"},
    {"text": "LSTM", "weight": 5, "lang": "en"},
    {"text": "GAN", "weight": 4, "lang": "en"},
    {"text": "NLP", "weight": 5, "lang": "en"},
    {"text": "CV", "weight": 4, "lang": "en"},
    # Chinese tech
    {"text": "大模型", "weight": 4, "lang": "zh"},
    {"text": "机器学习", "weight": 3, "lang": "zh"},
    {"text": "深度学习", "weight": 3, "lang": "zh"},
    {"text": "神经网络", "weight": 3, "lang": "zh"},
    {"text": "向量数据库", "weight": 4, "lang": "zh"},
    {"text": "知识图谱", "weight": 3, "lang": "zh"},
    {"text": "微服务", "weight": 3, "lang": "zh"},
    {"text": "容器化", "weight": 3, "lang": "zh"},
    {"text": "残差网络", "weight": 3, "lang": "zh"},
]

# Module-level vocabulary cache: (model, vocabulary_id)
_asr_vocab_cache: dict[str, str] = {}


def _ensure_asr_vocabulary(api_key: str, model: str) -> str | None:
    """Create or retrieve a hot-word vocabulary for the given ASR model.

    Caches the vocabulary_id in memory. Only creates a new vocabulary when
    the model changes or after a process restart.
    """
    if model in _asr_vocab_cache:
        return _asr_vocab_cache[model]

    try:
        import dashscope
        from dashscope.audio.asr import VocabularyService, VocabularyServiceException

        dashscope.api_key = api_key

        prefix = "aiview"  # ≤10 chars, lowercase
        svc = VocabularyService(api_key=api_key)

        # Reuse existing vocabulary with matching prefix
        try:
            vocab_list = svc.list_vocabularies(prefix=prefix, page_index=0, page_size=10)
            for item in vocab_list:
                if item.get("status") == "OK":
                    vid = item["vocabulary_id"]
                    _asr_vocab_cache[model] = vid
                    logger.info(
                        f"ASR hotwords: reused existing vocabulary_id={vid} "
                        f"for model={model}"
                    )
                    return vid
        except Exception:
            pass  # No existing vocabulary, create a new one

        vid = svc.create_vocabulary(
            target_model=model,
            prefix=prefix,
            vocabulary=ASR_HOTWORDS,
        )
        _asr_vocab_cache[model] = vid
        logger.info(
            f"ASR hotwords: created vocabulary_id={vid} "
            f"for model={model}, {len(ASR_HOTWORDS)} terms"
        )
        return vid

    except Exception as e:
        logger.warning(f"ASR hotwords: failed to init vocabulary: {e}")
        return None


class QwenASRProvider(BaseSTTProvider):
    """ASR via DashScope SDK (file-based Recognition.call).

    Supports paraformer-realtime-v2 / qwen3-asr-flash-realtime etc.
    Optionally uses hot-word vocabulary for better technical term accuracy.
    """

    ASR_TIMEOUT = 30  # seconds per recognition call
    MAX_STT_BYTES = 60 * 16000 * 2  # 60s at 16kHz 16bit

    def __init__(self, api_key: str = "", model: str = "", language: str = ""):
        self.api_key = api_key or settings.DASHSCOPE_API_KEY
        self.model = model or settings.DASHSCOPE_ASR_MODEL
        self.language = language or settings.DASHSCOPE_ASR_LANGUAGE
        logger.info(
            f"ASR bridge: provider init — model={self.model}, "
            f"language={self.language}, api_key={'***' if self.api_key else 'NOT SET'}"
        )
        # Init hot-word vocabulary (async-compatible: runs in thread on first use)
        self._vocabulary_id: str | None = None

    def _get_vocabulary_id(self) -> str | None:
        """Lazy-init hot-word vocabulary (called from thread pool)."""
        if self._vocabulary_id is None and self.api_key:
            self._vocabulary_id = _ensure_asr_vocabulary(self.api_key, self.model)
        return self._vocabulary_id

    def _do_transcribe(self, wav_path: str) -> str:
        """Synchronous SDK call — runs in thread pool."""
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionResult

        dashscope.api_key = self.api_key

        wav_size = os.path.getsize(wav_path)
        vocab_id = self._get_vocabulary_id()
        logger.info(
            "ASR bridge: invoking Recognition.call — "
            f"model={self.model}, wav_path={wav_path}, wav_size={wav_size}, "
            f"vocab_id={vocab_id[:12] + '...' if vocab_id else 'NONE'}"
        )

        recognition_kwargs = dict(
            model=self.model,
            callback=None,
            format="pcm",
            sample_rate=16000,
        )
        if vocab_id:
            recognition_kwargs["vocabulary_id"] = vocab_id

        recognition = Recognition(**recognition_kwargs)

        result = recognition.call(wav_path)
        sentences = result.get_sentence()

        if result.status_code != 200:
            logger.error(
                f"ASR bridge: API returned error — "
                f"status={result.status_code}, code={result.code}, "
                f"message={result.message}, request_id={result.request_id}"
            )

        if sentences is None:
            logger.warning(
                f"ASR bridge: no sentence in result — "
                f"status={result.status_code}, request_id={result.request_id}"
            )
            return ""

        # sentences can be a single dict or a list
        if isinstance(sentences, dict):
            text = sentences.get("text", "")
        elif isinstance(sentences, list):
            text = "".join(s.get("text", "") for s in sentences)
        else:
            text = ""

        logger.info(
            f"ASR bridge: transcription done — "
            f"status={result.status_code}, text_length={len(text)}, "
            f"request_id={result.request_id}"
        )
        return text

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        if not self.api_key:
            logger.warning("ASR bridge: DASHSCOPE_API_KEY not configured, returning empty")
            return ""
        if not audio_bytes or len(audio_bytes) < 1600:
            logger.debug(
                f"ASR bridge: audio too short ({len(audio_bytes) if audio_bytes else 0} bytes), skipping"
            )
            return ""
        if len(audio_bytes) > self.MAX_STT_BYTES:
            logger.warning(
                f"ASR bridge: audio too long ({len(audio_bytes)} bytes, "
                f"max {self.MAX_STT_BYTES}), truncating"
            )
            audio_bytes = audio_bytes[:self.MAX_STT_BYTES]

        logger.info(
            f"ASR bridge: transcribe start — model={self.model}, "
            f"audio_bytes={len(audio_bytes)}, sample_rate={sample_rate}"
        )

        # Write PCM to a temp WAV file (Recognition.call reads a file)
        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="qwen_asr_")
        os.close(fd)
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(AUDIO_SAMPLE_WIDTH)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)

            text = await asyncio.wait_for(
                asyncio.to_thread(self._do_transcribe, wav_path),
                timeout=self.ASR_TIMEOUT,
            )

            logger.info(f"ASR bridge: transcribe done — text_length={len(text)}")
            return text

        except asyncio.TimeoutError:
            logger.error(
                f"ASR bridge: timed out after {self.ASR_TIMEOUT}s — "
                f"model={self.model}, check network to dashscope.aliyuncs.com"
            )
            return ""
        except Exception:
            logger.exception(
                f"ASR bridge: transcribe failed — model={self.model}"
            )
            return ""
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


class QwenTTSProvider(BaseTTSProvider):
    """Qwen-TTS via DashScope MultiModalConversation (unified HTTP REST API).

    Uses MultiModalConversation.call() with stream=True, which returns audio
    as base64-encoded PCM chunks over HTTP SSE. Supports both legacy models
    (qwen-tts) and new models (qwen3-tts-flash, qwen3-tts-instruct-flash, etc.).
    Output is 24 kHz PCM 16-bit mono — frontend must use 24 kHz in WAV header.
    """

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        voice: str = "",
        language: str = "",
    ):
        self.api_key = api_key or settings.DASHSCOPE_API_KEY
        self.model = model or settings.DASHSCOPE_TTS_MODEL
        self.voice = voice or settings.DASHSCOPE_TTS_VOICE
        self.language = language or settings.DASHSCOPE_TTS_LANGUAGE
        logger.info(
            f"Qwen TTS bridge: provider init — model={self.model}, "
            f"voice={self.voice}, language={self.language}, "
            f"api_key={'***' if self.api_key else 'NOT SET'}"
        )

    def _do_synthesize(self, text: str) -> bytes:
        """Synchronous SDK call — runs in thread pool to avoid blocking."""
        import dashscope
        from dashscope.aigc.multimodal_conversation import MultiModalConversation

        dashscope.api_key = self.api_key

        logger.info(
            f"Qwen TTS bridge: invoking MultiModalConversation.call — "
            f"model={self.model}, text_len={len(text)}"
        )

        kwargs = dict(model=self.model, text=text, voice=self.voice, stream=True)
        kwargs["speech_rate"] = settings.TTS_SPEECH_RATE
        # language_type only for models that support it (e.g. qwen-tts uses 'zh')
        # qwen3-tts-instruct-flash auto-detects — passing it with wrong case fails
        if self.language:
            kwargs["language_type"] = self.language
        result = MultiModalConversation.call(**kwargs)

        audio_chunks: list[bytes] = []
        for rsp in result:
            if rsp.status_code != 200:
                logger.error(
                    f"Qwen TTS bridge: API returned error — "
                    f"status={rsp.status_code}, code={rsp.code}, "
                    f"message={rsp.message}, request_id={rsp.request_id}"
                )
                continue
            data = (rsp.output or {}).get("audio", {}).get("data", "")
            if data:
                audio_chunks.append(base64.b64decode(data))

        if not audio_chunks:
            logger.warning("Qwen TTS bridge: no audio data in response")
            return b""
        logger.info(f"Qwen TTS bridge: synthesis done — chunks={len(audio_chunks)}")
        return b"".join(audio_chunks)

    async def synthesize(self, text: str) -> bytes:
        if not self.api_key:
            logger.warning("Qwen TTS bridge: DASHSCOPE_API_KEY not configured, returning empty")
            return b""
        if not text or not text.strip():
            return b""

        try:
            pcm = await asyncio.to_thread(self._do_synthesize, text)
            if pcm:
                logger.info(f"Qwen TTS bridge: synthesize done — {len(pcm)} bytes")
            else:
                logger.warning("Qwen TTS bridge: returned no audio data")
            return pcm
        except Exception:
            logger.exception(f"Qwen TTS bridge: synthesize failed — model={self.model}")
            return b""


# ===== Provider Registry =====

STT_PROVIDERS: dict[str, type[BaseSTTProvider]] = {
    "aliyun": AliyunSTTProvider,
    "dashscope": QwenASRProvider,
}

TTS_PROVIDERS: dict[str, type[BaseTTSProvider]] = {
    "aliyun": AliyunTTSProvider,
    "dashscope": QwenTTSProvider,
}


# ===== Audio Handler =====


class AudioHandler:
    """Orchestrates audio processing for an interview session.

    Manages audio chunk accumulation, STT transcription, TTS synthesis,
    and final audio file merging.
    """

    def __init__(self):
        provider_name = settings.STT_PROVIDER
        if provider_name == "dashscope" and not settings.DASHSCOPE_API_KEY:
            logger.warning(
                "DASHSCOPE_API_KEY not set, falling back to Aliyun NLS for STT"
            )
            provider_name = "aliyun"
        stt_cls = STT_PROVIDERS.get(provider_name)
        self.stt: BaseSTTProvider = stt_cls() if stt_cls else AliyunSTTProvider()
        logger.info(
            f"AudioHandler bridge: STT provider={settings.STT_PROVIDER}, "
            f"impl={type(self.stt).__name__}, "
            f"dashscope_key={'***' if settings.DASHSCOPE_API_KEY else 'NOT SET'}"
        )

        provider_name = settings.TTS_PROVIDER
        if provider_name == "dashscope" and not settings.DASHSCOPE_API_KEY:
            logger.warning(
                "DASHSCOPE_API_KEY not set, falling back to Aliyun NLS for TTS"
            )
            provider_name = "aliyun"
        tts_cls = TTS_PROVIDERS.get(provider_name)
        self.tts: BaseTTSProvider = tts_cls() if tts_cls else AliyunTTSProvider()
        logger.info(
            f"AudioHandler bridge: TTS provider={settings.TTS_PROVIDER}, "
            f"impl={type(self.tts).__name__}"
        )

        # Per-interview temp file tracking
        self._chunk_files: dict[int, str] = {}
        # Per-interview in-memory utterance buffer (reset after each speech end)
        self._utterance_buffers: dict[int, bytearray] = {}

    # ===== STT / TTS =====

    async def speech_to_text(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text via cloud STT."""
        return await self.stt.transcribe(audio_bytes)

    async def text_to_speech(self, text: str) -> bytes:
        """Synthesize text to speech audio via cloud TTS."""
        return await self.tts.synthesize(text)

    # ===== Audio Chunk Management =====

    def append_chunk(self, interview_id: int, audio_bytes: bytes) -> None:
        """Append an audio frame to the interview's temp file and utterance buffer."""
        if interview_id not in self._chunk_files:
            fd, path = tempfile.mkstemp(suffix=".pcm", prefix=f"interview_{interview_id}_")
            os.close(fd)
            self._chunk_files[interview_id] = path
            logger.info(f"Created audio temp file: interview_id={interview_id}, path={path}")

        with open(self._chunk_files[interview_id], "ab") as f:
            f.write(audio_bytes)

        # Also buffer for per-utterance STT
        if interview_id not in self._utterance_buffers:
            self._utterance_buffers[interview_id] = bytearray()
        self._utterance_buffers[interview_id].extend(audio_bytes)

    def get_utterance_audio(self, interview_id: int) -> bytes:
        """Return accumulated utterance audio and reset the buffer."""
        buf = self._utterance_buffers.pop(interview_id, None)
        if buf is None:
            return b""
        return bytes(buf)

    async def merge_and_upload(self, interview_id: int, user_id: int | None = None) -> str:
        """Merge PCM chunks into a WAV file and upload to object storage.

        Returns the URL of the uploaded audio file, or an empty string on failure.
        """
        pcm_path = self._chunk_files.pop(interview_id, None)
        if not pcm_path:
            logger.warning(f"No audio data to merge: interview_id={interview_id}")
            return ""

        try:
            with open(pcm_path, "rb") as f:
                pcm_data = f.read()

            if not pcm_data:
                os.unlink(pcm_path)
                return ""

            wav_path = pcm_path.replace(".pcm", ".wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(AUDIO_CHANNELS)
                wf.setsampwidth(AUDIO_SAMPLE_WIDTH)
                wf.setframerate(AUDIO_SAMPLE_RATE)
                wf.writeframes(pcm_data)

            os.unlink(pcm_path)

            url = await self._upload(wav_path, interview_id, user_id)
            logger.info(f"Audio merged and uploaded: interview_id={interview_id}, url={url}")
            return url

        except Exception as e:
            logger.error(f"Audio merge failed: {e}", exc_info=True)
            if os.path.exists(pcm_path):
                os.unlink(pcm_path)
            return ""

    async def _upload(self, file_path: str, interview_id: int, user_id: int | None = None) -> str:
        """Upload audio file to object storage or local fallback."""
        filename = f"interview_{interview_id}_{os.path.basename(file_path)}"

        if settings.OSS_ENDPOINT and settings.OSS_ACCESS_KEY:
            try:
                import oss2
                auth = oss2.Auth(settings.OSS_ACCESS_KEY, settings.OSS_SECRET_KEY)
                bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET)
                bucket.put_object_from_file(f"audio/{filename}", file_path)
                url = f"https://{settings.OSS_BUCKET}.{settings.OSS_ENDPOINT}/audio/{filename}"
                os.unlink(file_path)
                return url
            except ImportError:
                logger.warning("oss2 not installed, using local storage")
            except Exception as e:
                logger.error(f"OSS upload failed: {e}")

        target_dir = os.path.join(settings.UPLOAD_DIR, "audio")
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, filename)
        shutil.move(file_path, target)

        url = f"/uploads/audio/{filename}"
        if user_id is not None:
            token = create_file_token(user_id, filename)
            url = f"{url}?token={token}"
        return url

    async def start_interview(self, interview_id: int) -> None:
        """Initialize audio recording for an interview."""
        self._chunk_files.pop(interview_id, None)
        self._utterance_buffers.pop(interview_id, None)

    async def end_interview(self, interview_id: int, user_id: int | None = None) -> str:
        """End recording and return the merged audio URL."""
        self._utterance_buffers.pop(interview_id, None)
        return await self.merge_and_upload(interview_id, user_id)
