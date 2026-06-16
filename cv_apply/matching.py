"""Matching semântico e por palavras-chave entre perfil e vagas."""

from __future__ import annotations

import logging
import os
import re

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

from cv_apply.profile import CandidateProfile, JobMatch, JobPosting
from cv_apply.skills_dict import find_skills, text_has_skill

logger = logging.getLogger(__name__)

_semantic_model = None
_semantic_available: bool | None = None


def _get_semantic_model():
    global _semantic_model, _semantic_available
    if _semantic_available is False:
        return None
    if _semantic_model is not None:
        return _semantic_model
    try:
        import logging as _logging

        for noisy in ("transformers", "sentence_transformers", "httpx", "huggingface_hub"):
            _logging.getLogger(noisy).setLevel(_logging.ERROR)

        from sentence_transformers import SentenceTransformer

        _semantic_model = SentenceTransformer("all-MiniLM-L6-v2")
        _semantic_available = True
        logger.info("Modelo semântico carregado: all-MiniLM-L6-v2")
        return _semantic_model
    except Exception as exc:
        logger.warning("Falha ao carregar sentence-transformers: %s. Usando TF-IDF.", exc)
        _semantic_available = False
        return None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def _semantic_similarity(text_a: str, text_b: str) -> float:
    model = _get_semantic_model()
    if model is not None:
        from sentence_transformers import util

        embeddings = model.encode(
            [text_a, text_b], convert_to_tensor=True, show_progress_bar=False
        )
        score = float(util.cos_sim(embeddings[0], embeddings[1]).item())
        return max(0.0, min(1.0, score))

    return _tfidf_similarity(text_a, text_b)


def _semantic_similarities(profile_text: str, job_texts: list[str]) -> list[float]:
    """Similaridade do perfil contra várias vagas (perfil codificado 1x)."""
    if not job_texts:
        return []

    model = _get_semantic_model()
    if model is not None:
        from sentence_transformers import util

        embeddings = model.encode(
            [profile_text] + job_texts,
            convert_to_tensor=True,
            show_progress_bar=False,
            batch_size=32,
        )
        sims = util.cos_sim(embeddings[0:1], embeddings[1:])[0]
        return [max(0.0, min(1.0, float(s))) for s in sims]

    return _tfidf_similarities(profile_text, job_texts)


def _tfidf_similarities(profile_text: str, job_texts: list[str]) -> list[float]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform([profile_text] + job_texts)
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
        return [max(0.0, min(1.0, float(s))) for s in sims]
    except Exception:
        return [0.0] * len(job_texts)


def _semantic_similarity(text_a: str, text_b: str) -> float:
    sims = _semantic_similarities(text_a, [text_b])
    return sims[0] if sims else 0.0


def _tfidf_similarity(text_a: str, text_b: str) -> float:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform([text_a, text_b])
        score = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.0


def _keyword_overlap(profile: CandidateProfile, job: JobPosting) -> tuple[float, list[str]]:
    """Sobreposição de skills entre perfil e vaga.

    O score prioriza a **cobertura das skills exigidas pela vaga** (quanto do que
    a vaga pede o candidato tem), em vez de dividir pelo total de skills do
    candidato — assim não penaliza quem tem um currículo amplo.
    """
    if not profile.skills:
        return 0.0, []

    job_text = _normalize(f"{job.title} {job.description}")
    matched = [skill for skill in profile.skills if text_has_skill(skill, job_text)]

    job_skills = find_skills(job_text)
    if job_skills:
        covered = sum(1 for js in job_skills if text_has_skill(js, " ".join(profile.skills).lower()))
        coverage = covered / len(job_skills)
        # mistura cobertura da vaga (peso maior) com proporção do candidato
        own_ratio = len(matched) / len(profile.skills)
        ratio = 0.7 * coverage + 0.3 * own_ratio
    else:
        ratio = len(matched) / len(profile.skills)

    return min(1.0, ratio), matched


def _seniority_score(profile: CandidateProfile, job: JobPosting) -> float:
    if not profile.seniority:
        return 0.5

    job_text = _normalize(f"{job.title} {job.description}")
    seniority_map = {
        "estagiário": ["estagiário", "estagiaria", "estágio", "intern", "trainee"],
        "júnior": ["júnior", "junior", "jr", "entry"],
        "pleno": ["pleno", "mid", "pl"],
        "sênior": ["sênior", "senior", "sr", "lead", "principal"],
    }
    profile_level = profile.seniority.lower()
    keywords = seniority_map.get(profile_level, [])

    for kw in keywords:
        if kw in job_text:
            return 1.0

    # Penalidade leve se vaga pede senioridade muito diferente
    if profile_level == "sênior" and any(k in job_text for k in ["júnior", "junior", "estágio"]):
        return 0.2
    if profile_level == "júnior" and any(k in job_text for k in ["sênior", "senior", "lead"]):
        return 0.3

    return 0.5


def _location_score(profile: CandidateProfile, job: JobPosting) -> float:
    job_loc = _normalize(job.location)
    if not job_loc:
        return 0.5

    remote_keywords = ["remoto", "remote", "home office", "anywhere", "híbrido", "hibrido"]
    if any(kw in job_loc for kw in remote_keywords):
        return 1.0

    if not profile.locations:
        return 0.5

    for loc in profile.locations:
        if _normalize(loc) in job_loc or job_loc in _normalize(loc):
            return 1.0

    if "brasil" in job_loc or "brazil" in job_loc:
        return 0.7

    return 0.3


def match_job(
    profile: CandidateProfile,
    job: JobPosting,
    use_semantic: bool = True,
    semantic_override: float | None = None,
) -> JobMatch:
    """Calcula score 0-100 e motivos para uma vaga.

    semantic_override permite passar a similaridade já calculada em lote
    (evita recodificar o perfil a cada vaga).
    """
    if semantic_override is not None:
        semantic = semantic_override
    elif use_semantic:
        profile_text = profile.profile_text()
        job_text = f"{job.title} {job.company} {job.description}"
        semantic = _semantic_similarity(profile_text, job_text)
    else:
        semantic = 0.0

    keyword_ratio, skill_overlap = _keyword_overlap(profile, job)
    seniority = _seniority_score(profile, job)
    location = _location_score(profile, job)

    # Pesos: semântico 40%, keywords 35%, senioridade 15%, local 10%
    if use_semantic and semantic > 0:
        raw_score = (
            semantic * 0.40
            + keyword_ratio * 0.35
            + seniority * 0.15
            + location * 0.10
        )
    else:
        raw_score = keyword_ratio * 0.55 + seniority * 0.25 + location * 0.20

    score = round(raw_score * 100, 1)
    reasons: list[str] = []

    if semantic >= 0.5:
        reasons.append(f"Alta similaridade semântica ({semantic:.0%})")
    elif semantic >= 0.3:
        reasons.append(f"Similaridade semântica moderada ({semantic:.0%})")

    if skill_overlap:
        reasons.append(f"Skills em comum: {', '.join(skill_overlap[:5])}")
    elif keyword_ratio == 0 and profile.skills:
        reasons.append("Poucas skills do currículo aparecem na vaga")

    if seniority >= 0.8:
        reasons.append("Senioridade compatível")
    elif seniority <= 0.3:
        reasons.append("Senioridade pode não combinar")

    if location >= 0.8:
        reasons.append("Localização/remoto compatível")

    if job.easy_apply:
        reasons.append("Easy Apply disponível")

    if not reasons:
        reasons.append("Match calculado com base no perfil geral")

    return JobMatch(
        job=job,
        score=score,
        reasons=reasons,
        skill_overlap=skill_overlap,
        semantic_score=round(semantic * 100, 1),
        keyword_score=round(keyword_ratio * 100, 1),
        seniority_score=round(seniority * 100, 1),
        location_score=round(location * 100, 1),
    )


def rank_jobs(
    profile: CandidateProfile,
    jobs: list[JobPosting],
    min_score: float = 0.0,
    use_semantic: bool = True,
) -> list[JobMatch]:
    """Ranqueia vagas por score decrescente.

    Calcula a similaridade semântica de todas as vagas em um único lote
    (perfil codificado uma vez), o que é muito mais rápido.
    """
    if not jobs:
        return []

    semantics: list[float | None] = [None] * len(jobs)
    if use_semantic:
        profile_text = profile.profile_text()
        job_texts = [f"{j.title} {j.company} {j.description}" for j in jobs]
        semantics = list(_semantic_similarities(profile_text, job_texts))

    matches = [
        match_job(profile, job, use_semantic=use_semantic, semantic_override=sem)
        for job, sem in zip(jobs, semantics, strict=False)
    ]
    matches = [m for m in matches if m.score >= min_score]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches
