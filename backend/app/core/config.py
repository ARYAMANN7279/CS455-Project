"""Application configuration via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "concord"
    app_env: Literal["dev", "test", "prod"] = "dev"

    secret_key: str = Field(default="dev-secret-change-me-32-bytes-minimum-len")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "postgresql+asyncpg://concord:concord@postgres:5432/concord"
    redis_url: str = "redis://redis:6379/0"

    # Sandbox
    sandbox_image: str = "concord-sandbox:latest"
    sandbox_mem_limit: str = "128m"
    sandbox_cpu_quota: int = 50000
    sandbox_pids_limit: int = 64
    sandbox_timeout_seconds: int = 10
    sandbox_network: str = "none"

    worker_concurrency: int = 2
    enable_debugger: bool = False

    # AI Assistant
    ai_assistant_enabled: bool = True
    ai_assistant_rate_limit_enabled: bool = True
    ai_assistant_rate_limit_requests: int = 10
    ai_assistant_rate_limit_window: int = 60  # seconds

    # AI Assistant Validation
    ai_assistant_validation_max_code_size: int = 10000  # characters

    # WebSocket
    websocket_heartbeat_interval: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
