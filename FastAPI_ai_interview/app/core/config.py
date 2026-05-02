"""Application configuration via pydantic-settings."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import ClassVar

# Resolve .env relative to this config file, so the app works regardless
# of the current working directory (IDE, systemd, etc.)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root"
    DB_NAME: str = "ai_interview"

    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 43200  # 30d

    # DeepSeek / LLM
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    LLM_MODEL: str = "deepseek-chat"

    # Redis
    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    # App
    APP_NAME: str = "AI Interview"
    APP_PORT: int = 8080
    DEBUG: bool = True
    DB_ECHO: bool = False
    # Absolute path to project-root uploads/ (not relative — CWD varies by runner)
    UPLOAD_DIR: str = str(
        Path(__file__).resolve().parent.parent.parent / "uploads"
    )
    FAISS_DIR: str = str(
        Path(__file__).resolve().parent.parent.parent / "data" / "faiss"
    )
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB

    # Scoring
    PASS_THRESHOLD: int = 60
    MAX_QUESTIONS_PER_STAGE: int = 5

    # Interview
    INTERVIEW_MAX_DURATION: int = 2700  # 45 minutes in seconds

    # STT/TTS — DashScope (Qwen-ASR-Realtime / Qwen-TTS-Realtime)
    STT_PROVIDER: str = "dashscope"
    TTS_PROVIDER: str = "dashscope"
    DASHSCOPE_API_KEY: str = ""

    # ASR — Qwen3-ASR-Flash Realtime (WebSocket)
    DASHSCOPE_ASR_MODEL: str = "qwen3-asr-flash-realtime"
    DASHSCOPE_ASR_LANGUAGE: str = "zh"

    # TTS — Qwen-TTS (MultiModalConversation HTTP REST API)
    # Models: qwen-tts / qwen3-tts-flash / qwen3-tts-instruct-flash
    # language_type: optional, empty = auto-detect; for qwen-tts use "zh"/"en"
    DASHSCOPE_TTS_MODEL: str = "qwen3-tts-flash"
    DASHSCOPE_TTS_VOICE: str = "Cherry"
    DASHSCOPE_TTS_LANGUAGE: str = ""

    # Legacy NLS (fallback when DASHSCOPE_API_KEY is empty)
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_NLS_APPKEY: str = ""

    # Alibaba Cloud SMS
    ALIYUN_SMS_SIGN_NAME: str = ""
    ALIYUN_SMS_TEMPLATE_REGISTER: str = ""
    ALIYUN_SMS_TEMPLATE_LOGIN: str = ""
    ALIYUN_SMS_TEMPLATE_RESET_PASSWORD: str = ""
    ALIYUN_SMS_CODE_LENGTH: int = 6
    ALIYUN_SMS_VALID_SECONDS: int = 300
    ALIYUN_SMS_RETRY_SECONDS: int = 60
    ALIYUN_SMS_MAX_DAILY: int = 10

    # Object storage
    OSS_ENDPOINT: str = ""
    OSS_BUCKET: str = ""
    OSS_ACCESS_KEY: str = ""
    OSS_SECRET_KEY: str = ""

    # Web search
    SEARCH_API_KEY: str = ""
    SEARCH_PROVIDER: str = "serper"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Rate Limit
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT: str = "60/minute"

    # Logging
    LOG_FORMAT: str = "plain"
    LOG_LEVEL: str = "INFO"
    LOG_LEVEL_APP: str = "DEBUG"
    LOG_LEVEL_ACCESS: str = "INFO"
    LOG_LEVEL_WATCHFILES: str = "WARNING"
    LOG_LEVEL_UVCORN: str = "WARNING"
    LOG_LEVEL_HTTPX: str = "WARNING"

    # Database URL (computed)
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Redis URL
    @property
    def REDIS_URL(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()