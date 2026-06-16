"""Setores/áreas de atuação e suas skills características.

O id do setor é compartilhado com o front-end (``static/app.js``). As skills
listadas aqui são usadas para dar um leve *boost* no ranqueamento: vagas que
mencionam as skills típicas da área escolhida sobem na lista.
"""

from __future__ import annotations

from cv_apply.profile import JobMatch
from cv_apply.skills_dict import text_has_skill

# id do setor → skills/termos característicos da área
SECTOR_SKILLS: dict[str, list[str]] = {
    "tec_dev": ["python", "java", "javascript", "react", "node.js", "api", "git"],
    "tec_suporte": ["suporte", "help desk", "windows", "linux", "redes", "hardware"],
    "tec_dados": ["sql", "python", "etl", "power bi", "data", "pandas", "spark"],
    "tec_devops": ["docker", "kubernetes", "terraform", "aws", "ci/cd", "linux"],
    "tec_qa": ["selenium", "cypress", "testes", "qa", "automação", "playwright"],
    "tec_seguranca": ["segurança", "pentest", "siem", "firewall", "soc"],
    "produto": ["product", "roadmap", "discovery", "métricas", "stakeholders"],
    "design": ["figma", "ux", "ui", "prototipação", "design system"],
    "marketing": ["seo", "google ads", "growth", "mídias sociais", "conteúdo"],
    "vendas": ["vendas", "crm", "prospecção", "negociação", "salesforce"],
    "atendimento": ["atendimento", "suporte ao cliente", "customer success", "sac"],
    "rh": ["recrutamento", "seleção", "departamento pessoal", "folha", "treinamento"],
    "financeiro": ["financeiro", "contas a pagar", "fluxo de caixa", "excel", "erp"],
    "fiscal": ["fiscal", "tributário", "icms", "sped", "nota fiscal"],
    "contabil": ["contabilidade", "balanço", "conciliação", "lançamentos", "dre"],
    "administrativo": ["administrativo", "rotinas", "excel", "organização"],
    "juridico": ["jurídico", "contratos", "processos", "petições", "compliance"],
    "logistica": ["logística", "estoque", "supply chain", "wms", "transporte"],
    "engenharia": ["engenharia", "autocad", "projetos", "manutenção"],
    "saude": ["enfermagem", "saúde", "paciente", "clínico"],
    "educacao": ["educação", "ensino", "didática", "pedagógico"],
    "outro": [],
}


def sector_skills(sector_id: str) -> list[str]:
    return SECTOR_SKILLS.get((sector_id or "").strip().lower(), [])


def apply_sector_boost(
    matches: list[JobMatch], sector_id: str, max_boost: float = 12.0
) -> list[JobMatch]:
    """Aumenta o score das vagas que mencionam skills do setor escolhido.

    O boost é proporcional à fração de skills da área presentes na vaga, limitado
    a ``max_boost`` pontos. A lista é reordenada por score ao final.
    """
    skills = sector_skills(sector_id)
    if not skills or not matches:
        return matches

    for m in matches:
        text = f"{m.job.title} {m.job.description}".lower()
        hits = sum(1 for s in skills if text_has_skill(s, text))
        if hits:
            boost = max_boost * (hits / len(skills))
            m.score = round(min(100.0, m.score + boost), 1)

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches
