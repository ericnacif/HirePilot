"""Configurações da aplicação via variáveis de ambiente."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parse_list(value: str) -> list[str]:
    """Converte 'a, b ,c' em ['a', 'b', 'c'] (minúsculo, sem vazios)."""
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


class Settings(BaseModel):
    resume_path: Path = Field(
        default_factory=lambda: Path(os.getenv("RESUME_PATH", "meu_cv.pdf"))
    )
    search_keywords: str = Field(
        default_factory=lambda: os.getenv("SEARCH_KEYWORDS", "desenvolvedor python")
    )
    search_location: str = Field(
        default_factory=lambda: os.getenv("SEARCH_LOCATION", "Brasil")
    )
    search_remote: bool = Field(
        default_factory=lambda: os.getenv("SEARCH_REMOTE", "true").lower() == "true"
    )
    search_sources: list[str] = Field(
        default_factory=lambda: _parse_list(os.getenv("SEARCH_SOURCES", "linkedin"))
    )
    search_workplace: list[str] = Field(
        default_factory=lambda: _parse_list(os.getenv("SEARCH_WORKPLACE", ""))
    )
    search_job_type: list[str] = Field(
        default_factory=lambda: _parse_list(os.getenv("SEARCH_JOB_TYPE", ""))
    )
    search_experience: list[str] = Field(
        default_factory=lambda: _parse_list(os.getenv("SEARCH_EXPERIENCE", ""))
    )
    search_date_posted: str = Field(
        default_factory=lambda: os.getenv("SEARCH_DATE_POSTED", "qualquer").lower()
    )
    daily_apply_limit: int = Field(
        default_factory=lambda: int(os.getenv("DAILY_APPLY_LIMIT", "10"))
    )
    min_match_score: float = Field(
        default_factory=lambda: float(os.getenv("MIN_MATCH_SCORE", "60"))
    )
    top_jobs_to_show: int = Field(
        default_factory=lambda: int(os.getenv("TOP_JOBS_TO_SHOW", "20"))
    )
    use_semantic_matching: bool = Field(
        default_factory=lambda: os.getenv("USE_SEMANTIC_MATCHING", "true").lower()
        == "true"
    )
    cover_letter_lang: str = Field(
        default_factory=lambda: os.getenv("COVER_LETTER_LANG", "auto").lower()
    )
    llm_provider: str = Field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "none").lower()
    )
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2")
    )
    groq_api_key: str = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = Field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    )
    browser_data_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("BROWSER_DATA_DIR", "browser_data"))
    )
    headless: bool = Field(
        default_factory=lambda: os.getenv("HEADLESS", "false").lower() == "true"
    )
    data_dir: Path = Field(default_factory=lambda: Path(os.getenv("DATA_DIR", "data")))

    def resolve_paths(self) -> "Settings":
        """Resolve caminhos relativos ao diretório do projeto."""
        if not self.resume_path.is_absolute():
            self.resume_path = PROJECT_ROOT / self.resume_path
        if not self.browser_data_dir.is_absolute():
            self.browser_data_dir = PROJECT_ROOT / self.browser_data_dir
        if not self.data_dir.is_absolute():
            self.data_dir = PROJECT_ROOT / self.data_dir
        # Compatibilidade: SEARCH_REMOTE=true vira workplace=remoto se nada definido
        if not self.search_workplace and self.search_remote:
            self.search_workplace = ["remoto"]
        if not self.search_sources:
            self.search_sources = ["linkedin"]
        return self


def get_settings() -> Settings:
    return Settings().resolve_paths()
