"""Configuration : tout vient du fichier .env (jamais de clé dans le code)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# revision/
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

APP_VERSION = "3.0"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    llm_provider: str  # auto | claude | gemini | groq | mock
    anthropic_api_key: str
    claude_model: str
    claude_effort: str
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str
    groq_model: str
    groq_vision_model: str
    youtube_api_key: str
    port: int
    run_worker: bool
    lesson_max_chars: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "revision.db"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "imports"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


@lru_cache
def get_config() -> Config:
    load_dotenv(ENV_FILE, override=False)
    data_dir = Path(_env("REVISION_DATA_DIR") or ROOT_DIR / "data")
    return Config(
        data_dir=data_dir,
        llm_provider=_env("LLM_PROVIDER", "auto").lower(),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        claude_model=_env("CLAUDE_MODEL", "claude-opus-5-5"),
        claude_effort=_env("CLAUDE_EFFORT", "medium").lower(),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-3.6-flash"),
        groq_api_key=_env("GROQ_API_KEY"),
        groq_model=_env("GROQ_MODEL", "auto"),
        groq_vision_model=_env("GROQ_VISION_MODEL", "auto"),
        youtube_api_key=_env("YOUTUBE_API_KEY"),
        port=int(_env("PORT", "8765")),
        run_worker=_env("REVISION_WORKER", "1") != "0",
        lesson_max_chars=int(_env("LESSON_MAX_CHARS", "30000")),
    )
