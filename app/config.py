"""Application settings (DOC_01 §3).

Loaded from environment / ``.env`` via pydantic-settings. In ``ENV=study`` the
required secrets must be present or startup fails fast.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["dev", "test", "study"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- secrets / connections ---
    database_url: str = "postgresql+asyncpg://eduverse:eduverse@localhost:5432/eduverse"
    anthropic_api_key: str = ""
    youtube_api_key: str = ""  # blank allowed for now; DOC_03 enforces at run time.
    voyage_api_key: str = ""  # DOC_03 embeddings; blank falls back to offline embedder.

    # --- model selection ---
    anthropic_model_reasoning: str = "claude-opus-4-7"
    anthropic_model_fast: str = "claude-sonnet-4-6"

    # --- content assembly (DOC_06) ---
    # Admin token guarding content regenerate/preview endpoints (DOC_06 §10).
    admin_token: str = ""
    # How many upcoming topics to warm up when a path is created (DOC_06 §9).
    content_pregeneration_count: int = 3

    # --- study reproducibility (DOC_08 §8) ---
    # Cache every Claude response keyed by (model, prompt_hash) for replay during
    # analysis. Disable only for local experiments where variety is wanted.
    llm_cache_enabled: bool = True

    # --- CORS ---
    # Browser origins allowed to call the API (the participant frontend). Comma-
    # separated; the deployed frontend URL(s) are added here in study.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- embeddings (DOC_03 §4.3) ---
    # voyage (default, needs VOYAGE_API_KEY) | local (sentence-transformers) |
    # hash (deterministic, offline; used by tests and offline dev).
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024

    # --- logging ---
    log_level: str = "INFO"
    log_file: str = "./logs/events.jsonl"

    # --- environment ---
    env: Env = "dev"

    @model_validator(mode="after")
    def _require_secrets_in_study(self) -> Settings:
        """DOC_01 §3: fail fast if required secrets are missing under study."""
        if self.env == "study":
            missing = [
                name
                for name, value in (
                    ("DATABASE_URL", self.database_url),
                    ("ANTHROPIC_API_KEY", self.anthropic_api_key),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"ENV=study requires {', '.join(missing)} to be set"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (one instance per process)."""
    return Settings()
