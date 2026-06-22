"""Configurações da aplicação via variáveis de ambiente."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _legacy_writable_bases() -> list[Path]:
    """Pastas de dados usadas antes do rebrand para HirePilot."""
    home = Path(os.path.expanduser("~"))
    if sys.platform.startswith("win"):
        root = Path(os.getenv("LOCALAPPDATA") or home)
        return [root / "VagaMatch"]
    return [home / ".vagamatch"]


def _user_writable_base() -> Path:
    """Pasta estável do usuário quando o app roda como executável empacotado."""
    if sys.platform.startswith("win"):
        root = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(root) / "HirePilot"
    return Path(os.path.expanduser("~")) / ".hirepilot"


def _migrate_legacy_data(new_base: Path, *, legacy_bases: list[Path] | None = None) -> None:
    """Move dados de VagaMatch/.vagamatch para HirePilot/.hirepilot (uma vez)."""
    marker = new_base / ".migrated_from_legacy"
    if marker.exists():
        return

    bases = legacy_bases if legacy_bases is not None else _legacy_writable_bases()
    for old_base in bases:
        if not old_base.is_dir() or old_base.resolve() == new_base.resolve():
            continue
        try:
            has_content = any(old_base.iterdir())
        except OSError:
            continue
        if not has_content:
            continue

        new_base.mkdir(parents=True, exist_ok=True)
        migrated_from = None
        for item in old_base.iterdir():
            dest = new_base / item.name
            if dest.exists():
                logger.debug("Migração: destino já existe, pulando %s", dest)
                continue
            try:
                shutil.move(str(item), str(dest))
                migrated_from = old_base
            except OSError as exc:
                logger.warning("Não foi possível migrar %s → %s: %s", item, dest, exc)

        if migrated_from is None:
            continue

        try:
            if old_base.is_dir() and not any(old_base.iterdir()):
                old_base.rmdir()
        except OSError:
            pass

        marker.write_text(str(migrated_from), encoding="utf-8")
        logger.info("Dados migrados de %s para %s", migrated_from, new_base)
        return


def _writable_base() -> Path:
    """Base para arquivos graváveis (uploads/dados).

    No executável empacotado (PyInstaller), ``PROJECT_ROOT`` aponta para uma
    pasta temporária somente-leitura; usamos então uma pasta estável do usuário
    (``%LOCALAPPDATA%\\HirePilot`` no Windows, ``~/.hirepilot`` nos demais).
    """
    if getattr(sys, "frozen", False):
        new_base = _user_writable_base()
        _migrate_legacy_data(new_base)
        return new_base
    return PROJECT_ROOT


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
    search_queries: list[str] = Field(default_factory=list)
    broad_mode: bool = Field(
        default_factory=lambda: os.getenv("SEARCH_BROAD", "true").lower() == "true"
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
    jooble_api_key: str = Field(default_factory=lambda: os.getenv("JOOBLE_API_KEY", ""))
    careerjet_api_key: str = Field(default_factory=lambda: os.getenv("CAREERJET_API_KEY", ""))

    def resolve_paths(self) -> Settings:
        """Resolve caminhos relativos ao diretório do projeto.

        Arquivos graváveis (dados/uploads) usam :func:`_writable_base`, que aponta
        para uma pasta do usuário quando o app roda como executável empacotado.
        """
        base = _writable_base()
        if not self.resume_path.is_absolute():
            self.resume_path = base / self.resume_path
        if not self.browser_data_dir.is_absolute():
            self.browser_data_dir = base / self.browser_data_dir
        if not self.data_dir.is_absolute():
            self.data_dir = base / self.data_dir
        # Compatibilidade: SEARCH_REMOTE=true vira workplace=remoto se nada definido
        if not self.search_workplace and self.search_remote:
            self.search_workplace = ["remoto"]
        if not self.search_sources:
            self.search_sources = ["linkedin"]
        return self


def get_settings() -> Settings:
    return Settings().resolve_paths()
