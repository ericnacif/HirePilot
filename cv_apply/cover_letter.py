"""Geração de carta de apresentação por template ou LLM gratuito.

Suporta português e inglês. O idioma pode ser detectado automaticamente a
partir da vaga ou definido manualmente.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import httpx
from jinja2 import Template

from cv_apply.config import Settings
from cv_apply.profile import CandidateProfile, JobPosting

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """Prezado(a) recrutador(a) da {{ company }},

Tenho grande interesse na vaga de {{ job_title }} e acredito que meu perfil tem forte aderência à oportunidade.

{% if candidate_name %}Meu nome é {{ candidate_name }}.{% endif %} {% if seniority %}Atuo como profissional {{ seniority }}{% if years_experience %}, com cerca de {{ years_experience }} anos de experiência{% endif %}.{% endif %}

{% if matched_skills %}Vi que a vaga valoriza {{ matched_skills }} — tecnologias com as quais já trabalho diretamente.{% elif skills %}Minhas principais competências incluem: {{ skills }}.{% endif %}

{% if summary %}{{ summary }}{% else %}Busco contribuir com entregas de qualidade e crescer junto com o time da {{ company }}.{% endif %}

Fico à disposição para conversarmos sobre como posso agregar ao time.

Atenciosamente,
{% if candidate_name %}{{ candidate_name }}{% else %}Candidato(a){% endif %}
{% if email %}{{ email }}{% endif %}
"""

ENGLISH_TEMPLATE = """Dear Hiring Manager at {{ company }},

I am very interested in the {{ job_title }} position and believe my background is a strong fit for this opportunity.

{% if candidate_name %}My name is {{ candidate_name }}.{% endif %} {% if seniority %}I work as a {{ seniority }} professional{% if years_experience %}, with around {{ years_experience }} years of experience{% endif %}.{% endif %}

{% if matched_skills %}I noticed the role values {{ matched_skills }} — technologies I work with directly.{% elif skills %}My core skills include: {{ skills }}.{% endif %}

{% if summary %}{{ summary }}{% else %}I am eager to deliver quality work and grow together with the {{ company }} team.{% endif %}

I would welcome the chance to discuss how I can contribute to your team.

Best regards,
{% if candidate_name %}{{ candidate_name }}{% else %}Candidate{% endif %}
{% if email %}{{ email }}{% endif %}
"""

_SENIORITY_EN = {
    "estagiário": "intern",
    "júnior": "junior",
    "pleno": "mid-level",
    "sênior": "senior",
}

# Palavras comuns para distinguir português de inglês
_PT_HINTS = {
    "vaga", "experiência", "experiencia", "conhecimento", "trabalho",
    "habilidades", "requisitos", "atividades", "empresa", "desenvolvimento",
    "responsabilidades", "para", "com", "você", "nós", "será", "área",
    "equipe", "ferramentas", "diferenciais", "benefícios",
}
_EN_HINTS = {
    "experience", "skills", "requirements", "responsibilities", "team",
    "company", "knowledge", "work", "the", "and", "with", "you", "we",
    "will", "role", "must", "ability", "strong", "benefits", "about",
}


def detect_language(text: str) -> str:
    """Retorna 'en' ou 'pt' com base nas palavras mais frequentes do texto."""
    if not text:
        return "pt"
    words = re.findall(r"[a-zA-ZáàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]+", text.lower())
    if not words:
        return "pt"
    pt = sum(1 for w in words if w in _PT_HINTS)
    en = sum(1 for w in words if w in _EN_HINTS)
    return "en" if en > pt else "pt"


def resolve_language(job: JobPosting, settings: Settings, override: Optional[str] = None) -> str:
    """Decide o idioma da carta: override > config > detecção automática."""
    lang = (override or getattr(settings, "cover_letter_lang", "auto") or "auto").lower()
    if lang in ("pt", "en"):
        return lang
    return detect_language(f"{job.title} {job.description}")


def _matched_skills_for_job(profile: CandidateProfile, job: JobPosting) -> list[str]:
    """Skills do candidato que aparecem na descrição da vaga."""
    try:
        from cv_apply.ats import extract_job_keywords

        job_keywords = {k.lower() for k in extract_job_keywords(job)}
        return [s for s in profile.skills if s.lower() in job_keywords]
    except Exception:
        return []


def generate_cover_letter_template(
    profile: CandidateProfile,
    job: JobPosting,
    template_str: Optional[str] = None,
    lang: str = "pt",
) -> str:
    matched = _matched_skills_for_job(profile, job)
    if template_str is None:
        template_str = ENGLISH_TEMPLATE if lang == "en" else DEFAULT_TEMPLATE

    seniority = profile.seniority or ""
    if lang == "en" and seniority:
        seniority = _SENIORITY_EN.get(seniority, seniority)

    template = Template(template_str)
    return template.render(
        company=job.company,
        job_title=job.title,
        candidate_name=profile.name or "",
        seniority=seniority,
        skills=", ".join(profile.skills[:8]) if profile.skills else "",
        matched_skills=", ".join(matched[:6]) if matched else "",
        years_experience=profile.years_experience or "",
        summary=profile.summary or "",
        email=profile.email or "",
    ).strip()


def _llm_prompt(profile: CandidateProfile, job: JobPosting, lang: str) -> str:
    summary = profile.summary or profile.raw_text[:500]
    if lang == "en":
        return f"""Write a short cover letter (max 200 words) in English
for the {job.title} position at {job.company}.

Candidate profile:
- Name: {profile.name or 'Not provided'}
- Skills: {', '.join(profile.skills[:10])}
- Seniority: {profile.seniority or 'Not provided'}
- Summary: {summary}

Job description (excerpt):
{job.description[:800]}

Be professional, concise and tailor it to the role. Do not invent experience."""

    return f"""Escreva uma carta de apresentação curta (máximo 200 palavras) em português brasileiro
para a vaga de {job.title} na empresa {job.company}.

Perfil do candidato:
- Nome: {profile.name or 'Não informado'}
- Skills: {', '.join(profile.skills[:10])}
- Senioridade: {profile.seniority or 'Não informada'}
- Resumo: {summary}

Descrição da vaga (trecho):
{job.description[:800]}

Seja profissional, objetivo e personalize para a vaga. Não invente experiências."""


def _generate_ollama(
    profile: CandidateProfile,
    job: JobPosting,
    settings: Settings,
    lang: str = "pt",
) -> str:
    prompt = _llm_prompt(profile, job, lang)

    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()


def _generate_groq(
    profile: CandidateProfile,
    job: JobPosting,
    settings: Settings,
    lang: str = "pt",
) -> str:
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY não configurada no .env")

    prompt = _llm_prompt(profile, job, lang)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.groq_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.7,
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


def generate_cover_letter(
    profile: CandidateProfile,
    job: JobPosting,
    settings: Settings,
    lang: Optional[str] = None,
) -> str:
    """Gera carta por template ou LLM configurado, no idioma resolvido.

    lang: 'pt', 'en' ou None (usa config/detecção automática pela vaga).
    """
    language = resolve_language(job, settings, override=lang)
    provider = settings.llm_provider.lower()

    if provider == "ollama":
        try:
            return _generate_ollama(profile, job, settings, language)
        except Exception as exc:
            logger.warning("Ollama falhou (%s). Usando template.", exc)
            return generate_cover_letter_template(profile, job, lang=language)

    if provider == "groq":
        try:
            return _generate_groq(profile, job, settings, language)
        except Exception as exc:
            logger.warning("Groq falhou (%s). Usando template.", exc)
            return generate_cover_letter_template(profile, job, lang=language)

    return generate_cover_letter_template(profile, job, lang=language)
