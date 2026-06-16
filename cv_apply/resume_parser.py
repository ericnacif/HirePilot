"""Parser de currículo PDF/DOCX para CandidateProfile."""

from __future__ import annotations

import re
from pathlib import Path

from cv_apply.profile import CandidateProfile
from cv_apply.skills_dict import JOB_TITLE_PATTERNS, SENIORITY_KEYWORDS, find_skills


def extract_text_from_pdf(path: Path) -> str:
    import pdfplumber

    text_parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_text_from_docx(path: Path) -> str:
    from docx import Document

    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix in (".docx", ".doc"):
        return extract_text_from_docx(path)
    raise ValueError(f"Formato não suportado: {suffix}. Use PDF ou DOCX.")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def extract_email(text: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else None


def extract_phone(text: str) -> str | None:
    patterns = [
        r"\+?55\s?\(?\d{2}\)?\s?\d{4,5}[-.\s]?\d{4}",
        r"\+?\d{1,3}[-.\s]?\(?\d{2,3}\)?[-.\s]?\d{4,5}[-.\s]?\d{4}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def extract_name(text: str) -> str | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    first = lines[0]
    if "@" in first or re.search(r"\d{3,}", first):
        return None
    if len(first.split()) <= 6 and len(first) < 60:
        return first
    return None


def extract_skills(text: str) -> list[str]:
    return find_skills(text)


def extract_seniority(text: str) -> str | None:
    """Detecta a senioridade do cargo ATUAL.

    Considera apenas o topo do currículo (cabeçalho, cargo e resumo), onde fica
    o cargo atual. Isso evita rotular como "estagiário" alguém que apenas teve
    um estágio no passado (mencionado na seção de experiência). Quando o nível
    não está explícito no topo, retorna None (não informado) em vez de chutar.
    """
    if not text.strip():
        return None

    lines = [ln for ln in text.splitlines() if ln.strip()]
    top_text = _normalize(" ".join(lines[:12]))

    scores: dict[str, int] = {}
    for level, keywords in SENIORITY_KEYWORDS.items():
        count = 0
        for kw in keywords:
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            count += len(re.findall(pattern, top_text))
        if count:
            scores[level] = count

    if not scores:
        return None

    # maior contagem; empate vai para a senioridade mais alta
    order = list(SENIORITY_KEYWORDS.keys())
    return max(scores, key=lambda lvl: (scores[lvl], order.index(lvl)))


def extract_job_titles(text: str) -> list[str]:
    titles: list[str] = []
    lines = text.splitlines()
    for line in lines:
        line_norm = _normalize(line)
        for pattern in JOB_TITLE_PATTERNS:
            if pattern in line_norm and len(line.strip()) < 80:
                titles.append(line.strip())
                break
    return list(dict.fromkeys(titles))[:5]


def extract_years_experience(text: str) -> int | None:
    patterns = [
        r"(\d+)\s*\+?\s*anos?\s*(de\s*)?(experiência|experiencia|experience)",
        r"(\d+)\s*\+?\s*years?\s*(of\s*)?experience",
    ]
    normalized = _normalize(text)
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return int(match.group(1))
    return None


LOCATION_TERMS = [
    # Brasil — cidades
    "são paulo", "rio de janeiro", "belo horizonte", "curitiba", "porto alegre",
    "brasília", "salvador", "recife", "fortaleza", "campinas", "florianópolis",
    # Brasil / país
    "brasil", "brazil",
    # Europa
    "lisboa", "lisbon", "porto", "madrid", "barcelona", "london", "londres",
    "manchester", "dublin", "berlin", "berlim", "munich", "munique", "amsterdam",
    "amsterdã", "paris", "rome", "roma", "milan", "milão", "warsaw", "varsóvia",
    "portugal", "spain", "espanha", "germany", "alemanha", "france", "frança",
    "netherlands", "holanda", "ireland", "irlanda", "united kingdom", "uk",
    "reino unido", "italy", "itália", "poland", "polônia", "europe", "europa",
    # Américas / outros
    "new york", "nova york", "san francisco", "toronto", "vancouver",
    "buenos aires", "mexico city", "cidade do méxico", "united states", "usa",
    "eua", "estados unidos", "canada", "canadá", "argentina", "mexico", "méxico",
    "latam", "emea",
    # Modelos de trabalho
    "remoto", "remote", "híbrido", "hibrido", "hybrid", "anywhere", "worldwide",
]


def extract_locations(text: str) -> list[str]:
    normalized = _normalize(text)
    found = [term.title() for term in LOCATION_TERMS if term in normalized]
    return list(dict.fromkeys(found))


def extract_summary(text: str) -> str | None:
    keywords = ["resumo", "summary", "sobre mim", "about me", "perfil", "profile"]
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if any(kw in _normalize(line) for kw in keywords):
            summary_lines = []
            for j in range(i + 1, min(i + 6, len(lines))):
                if lines[j].strip():
                    summary_lines.append(lines[j].strip())
            if summary_lines:
                return " ".join(summary_lines)
    return None


def parse_resume(path: Path) -> CandidateProfile:
    """Extrai perfil estruturado de um currículo PDF ou DOCX."""
    if not path.exists():
        raise FileNotFoundError(f"Currículo não encontrado: {path}")

    raw_text = extract_text(path)
    if not raw_text.strip():
        raise ValueError(f"Não foi possível extrair texto de: {path}")

    return CandidateProfile(
        name=extract_name(raw_text),
        email=extract_email(raw_text),
        phone=extract_phone(raw_text),
        summary=extract_summary(raw_text),
        skills=extract_skills(raw_text),
        job_titles=extract_job_titles(raw_text),
        seniority=extract_seniority(raw_text),
        locations=extract_locations(raw_text),
        years_experience=extract_years_experience(raw_text),
        raw_text=raw_text,
    )
