"""Modelos de dados do candidato e das vagas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    """Perfil extraído do currículo."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    seniority: str | None = None
    locations: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    raw_text: str = ""

    def profile_text(self) -> str:
        """Texto consolidado para matching semântico."""
        parts = [
            self.headline or "",
            self.summary or "",
            " ".join(self.skills),
            " ".join(self.job_titles),
            self.seniority or "",
            " ".join(self.locations),
            self.raw_text,
        ]
        return " ".join(p for p in parts if p).strip()


class JobPosting(BaseModel):
    """Vaga encontrada no LinkedIn."""

    id: str
    title: str
    company: str
    location: str = ""
    url: str
    description: str = ""
    easy_apply: bool = False
    posted_at: str | None = None
    scraped_at: datetime = Field(default_factory=datetime.now)


class JobMatch(BaseModel):
    """Resultado do matching entre perfil e vaga."""

    job: JobPosting
    score: float
    reasons: list[str] = Field(default_factory=list)
    skill_overlap: list[str] = Field(default_factory=list)
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    seniority_score: float = 0.0
    location_score: float = 0.0
    missing_skills: list[str] = Field(default_factory=list)
    breakdown: dict[str, float] = Field(default_factory=dict)
    fit_label: str = ""
