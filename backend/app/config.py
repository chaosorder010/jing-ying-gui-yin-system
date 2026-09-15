from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://jygy:jygy_secret@localhost:55433/jing_ying_gui_yin"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8001"
    auth_mode: str = "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    data_root: Path = Path(__file__).resolve().parents[2].parent / "data"
    upload_root: Path = Path(__file__).resolve().parents[2].parent / "uploads"
    export_root: Path = Path(__file__).resolve().parents[2].parent / "exports"
    workspace_root: Path = Path(__file__).resolve().parents[2].parent / "workspace"
    ws_token_ttl_seconds: int = 300
    context_summary_threshold: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
