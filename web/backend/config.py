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
    LLM_API_KEY_ENV: str = os.getenv("LLM_API_KEY_ENV", "GROQ_API_KEY")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    PROJECT_ROOT: Path = _PROJECT_ROOT
    DATA_DIR: Path = _PROJECT_ROOT / "data"


settings = Settings()
