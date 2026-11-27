from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình AI service (QĐ-HARNESS-002, QĐ-HARNESS-007, QĐ-HARNESS-014)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    be_base_url: str = "http://127.0.0.1:8001"
    router_mode: Literal["small_only", "hybrid", "cloud_only"] = "small_only"

    small_model_base_url: str = "http://localhost:11434/v1"
    small_model_name: str = "qwen2.5:7b"
    small_timeout_s: float = 8.0
    small_max_concurrency: int = 4

    cloud_model: str = ""
    cloud_api_key: str = ""
    cloud_backup_model: str = ""
    cloud_backup_api_key: str = ""
    cloud_timeout_s: float = 30.0

    supabase_db_url: str = ""

    daily_message_limit: int = 60
    max_tool_steps: int = 6
    max_schema_retries: int = 2
    pending_ttl_min: int = 30
    proactive_daily_limit: int = 3
    max_response_tokens: int = 800
    be_timeout_s: float = 10.0
    settings_cache_ttl_s: int = 60
    tz: str = "Asia/Ho_Chi_Minh"


@lru_cache
def get_settings() -> Settings:
    """Trả về singleton Settings đọc từ môi trường."""
    return Settings()
