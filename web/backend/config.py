from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{_PROJECT_ROOT / 'data' / 'translator_memory.db'}",
    )
    # High-quality prose repair. Existing LLM_* values remain supported so
    # deployments do not need to migrate their environment variables at once.
    REWRITE_LLM_API_KEY_ENV: str = os.getenv("REWRITE_LLM_API_KEY_ENV", os.getenv("LLM_API_KEY_ENV", "GROQ_API_KEY"))
    REWRITE_LLM_MODEL: str = os.getenv("REWRITE_LLM_MODEL", os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"))
    REWRITE_LLM_BASE_URL: str = os.getenv(
        "REWRITE_LLM_BASE_URL", os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    )
    REWRITE_LLM_TEMPERATURE: float = float(os.getenv("REWRITE_LLM_TEMPERATURE", "0.25"))
    REWRITE_LLM_MAX_TOKENS: int = int(os.getenv("REWRITE_LLM_MAX_TOKENS", "3072"))
    ENABLE_ALIAS_BRIDGING: bool = os.getenv("ENABLE_ALIAS_BRIDGING", "false").lower() == "true"

    # Cheap policy/entity verification. This defaults to a local OpenAI-
    # compatible llama.cpp server and is intentionally separate from prose repair.
    LOCAL_LLM_BASE_URL: str = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "local-model")
    LOCAL_LLM_API_KEY: str = os.getenv("LOCAL_LLM_API_KEY", "sk-no-key-required")

    # Backwards-compatible aliases for existing callers.
    LLM_API_KEY_ENV: str = REWRITE_LLM_API_KEY_ENV
    LLM_MODEL: str = REWRITE_LLM_MODEL
    LLM_BASE_URL: str = REWRITE_LLM_BASE_URL

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    PROJECT_ROOT: Path = _PROJECT_ROOT
    DATA_DIR: Path = _PROJECT_ROOT / "data"


settings = Settings()
