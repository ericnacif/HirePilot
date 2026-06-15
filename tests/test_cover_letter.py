"""Testes da carta de apresentação multilíngue (template, sem LLM)."""

from cv_apply.config import Settings
from cv_apply.cover_letter import (
    detect_language,
    generate_cover_letter_template,
    resolve_language,
)
from cv_apply.profile import CandidateProfile, JobPosting


def _job(title, description):
    return JobPosting(id="1", title=title, company="Acme", url="http://x", description=description)


def test_detect_language():
    en = _job("Developer", "We are looking for a developer with experience and strong skills.")
    pt = _job("Desenvolvedor", "Buscamos desenvolvedor com experiência e conhecimento na área.")
    assert detect_language(f"{en.title} {en.description}") == "en"
    assert detect_language(f"{pt.title} {pt.description}") == "pt"


def test_resolve_language_override_tem_prioridade():
    settings = Settings(cover_letter_lang="auto")
    job = _job("Developer", "experience skills team requirements")
    assert resolve_language(job, settings, override="pt") == "pt"
    assert resolve_language(job, settings, override="en") == "en"


def test_resolve_language_config_fixa():
    settings = Settings(cover_letter_lang="pt")
    job = _job("Developer", "experience skills team requirements role")
    assert resolve_language(job, settings) == "pt"


def test_template_pt():
    profile = CandidateProfile(name="Eric", seniority="júnior", skills=["python"])
    letter = generate_cover_letter_template(profile, _job("Dev", "python"), lang="pt")
    assert "Prezado" in letter
    assert "Eric" in letter


def test_template_en_traduz_senioridade():
    profile = CandidateProfile(name="Eric", seniority="júnior", skills=["python"])
    letter = generate_cover_letter_template(profile, _job("Dev", "python"), lang="en")
    assert "Dear Hiring Manager" in letter
    assert "junior" in letter
    assert "júnior" not in letter
