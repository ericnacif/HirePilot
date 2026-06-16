"""Setores/áreas de atuação e suas skills características.

O id do setor é compartilhado com o front-end (``static/app.js``). As skills
listadas aqui são usadas para dar um leve *boost* no ranqueamento: vagas que
mencionam as skills típicas da área escolhida sobem na lista.
"""

from __future__ import annotations

from cv_apply.profile import JobMatch
from cv_apply.skills_dict import text_has_skill

# id do setor → termo de busca primário (conciso). Usado como query nas fontes
# quando o usuário NÃO digita palavras-chave próprias. Frases curtas funcionam
# melhor em APIs que casam o texto de forma quase literal (Gupy/InfoJobs).
SECTOR_PRIMARY_TERM: dict[str, str] = {
    "tec_all": "tecnologia",
    "tec_dev": "desenvolvedor",
    "tec_suporte": "suporte técnico",
    "tec_dados": "analista de dados",
    "tec_devops": "devops",
    "tec_qa": "analista de testes",
    "tec_seguranca": "segurança da informação",
    "produto": "product manager",
    "design": "designer",
    "marketing": "marketing",
    "vendas": "vendas",
    "atendimento": "atendimento ao cliente",
    "rh": "recursos humanos",
    "financeiro": "analista financeiro",
    "fiscal": "fiscal",
    "contabil": "contabilidade",
    "administrativo": "administrativo",
    "juridico": "jurídico",
    "logistica": "logística",
    "engenharia": "engenharia",
    "saude": "saúde",
    "educacao": "professor",
    "outro": "",
    "emprego_geral": "auxiliar administrativo",
    "varejo": "vendedor",
    "servicos": "serviços gerais",
    "operacional": "operador de produção",
    "primeiro_emprego": "auxiliar",
    "limpeza": "auxiliar de limpeza",
    "motorista": "motorista",
    "cozinha": "cozinheiro",
}


def sector_query(sector_id: str) -> str:
    """Termo de busca representativo do setor (ou '' se não houver)."""
    return SECTOR_PRIMARY_TERM.get((sector_id or "").strip().lower(), "")


# Várias consultas por setor — a Gupy/InfoJobs casam ``jobName`` de forma literal,
# então buscamos com termos diferentes e unimos os resultados (deduplicados).
SECTOR_SEARCH_QUERIES: dict[str, list[str]] = {
    "tec_all": [
        "tecnologia", "ti", "desenvolvedor", "programador", "analista",
        "engenheiro", "software", "informática", "sistemas",
    ],
    "tec_dev": [
        "desenvolvedor", "programador", "software", "engenheiro de software",
        "full stack", "backend", "frontend", "web",
    ],
    "tec_suporte": [
        "suporte técnico", "help desk", "analista de suporte", "service desk", "ti",
    ],
    "tec_dados": [
        "dados", "data", "analista de dados", "cientista de dados", "bi", "engenheiro de dados",
    ],
    "tec_devops": ["devops", "sre", "infraestrutura", "cloud", "platform engineer"],
    "tec_qa": ["qa", "qualidade", "testes", "analista de testes", "automação de testes"],
    "tec_seguranca": ["segurança", "cyber", "soc", "pentest", "information security"],
    "produto": ["product manager", "product owner", "gerente de produto", "produto"],
    "design": ["designer", "ux", "ui", "product design", "experiência"],
    "marketing": ["marketing", "growth", "mídia", "conteúdo", "seo"],
    "vendas": ["vendas", "comercial", "inside sales", "account executive", "sdr"],
    "atendimento": ["atendimento", "customer success", "suporte ao cliente", "sac"],
    "rh": ["recursos humanos", "rh", "recrutamento", "seleção", "talent acquisition"],
    "financeiro": ["financeiro", "controladoria", "analista financeiro", "fp&a"],
    "fiscal": ["fiscal", "tributário", "impostos", "tax"],
    "contabil": ["contábil", "contabilidade", "contador", "accounting"],
    "administrativo": ["administrativo", "assistente administrativo", "back office"],
    "juridico": ["jurídico", "advogado", "legal", "compliance"],
    "logistica": ["logística", "supply chain", "estoque", "expedição"],
    "engenharia": ["engenheiro", "engenharia", "projetos", "manutenção"],
    "saude": ["saúde", "enfermagem", "médico", "clínico", "hospitalar"],
    "educacao": ["professor", "educação", "ensino", "pedagógico", "instrutor"],
    "emprego_geral": [
        "auxiliar", "assistente", "operador", "atendente", "recepcionista",
        "balconista", "office boy", "office-boy", "aprendiz",
    ],
    "varejo": ["vendedor", "vendedora", "caixa", "loja", "atendente", "balconista", "varejo"],
    "servicos": ["serviços gerais", "manutenção", "zelador", "porteiro", "jardineiro"],
    "operacional": ["produção", "operador", "estoque", "expedição", "almoxarifado", "fábrica"],
    "primeiro_emprego": ["aprendiz", "jovem aprendiz", "trainee", "auxiliar", "estágio", "iniciante"],
    "limpeza": ["limpeza", "faxina", "auxiliar de limpeza", "serviços gerais"],
    "motorista": ["motorista", "entregador", "cnh", "caminhão", "motoboy"],
    "cozinha": ["cozinheiro", "cozinheira", "auxiliar de cozinha", "restaurante", "buffet"],
}


def sector_search_queries(sector_id: str) -> list[str]:
    """Termos de busca a rodar nas fontes (união dos resultados)."""
    sid = (sector_id or "").strip().lower()
    if sid in SECTOR_SEARCH_QUERIES:
        return list(SECTOR_SEARCH_QUERIES[sid])
    primary = sector_query(sid)
    return [primary] if primary else []


# Tokens genéricos que não ajudam a discriminar relevância de área.
_GENERIC_SECTOR_TOKENS = {
    "de", "da", "do", "ao", "e", "técnico", "tecnico", "analista", "assistente",
    "desenvolvedor", "desenvolvedora", "programador", "coordenador", "gerente",
    "manager", "consultor", "especialista", "auxiliar", "profissional",
}

# Skills muito comuns que aparecem em descrições de vagas não relacionadas
# (ex.: "api", "git" em textos genéricos). Servem para boost, mas são fracas
# demais como filtro de relevância de área.
_WEAK_GATE_TOKENS = {"api", "git", "excel", "office"}


def sector_gate_terms(sector_id: str) -> list[str]:
    """Termos para filtrar relevância quando o usuário escolhe um setor mas não
    digita palavras-chave próprias: as skills da área + tokens do termo primário.
    """
    sid = (sector_id or "").strip().lower()
    terms = [s for s in sector_skills(sid) if s not in _WEAK_GATE_TOKENS]
    for tok in sector_query(sid).split():
        t = tok.strip().lower()
        if len(t) > 2 and t not in _GENERIC_SECTOR_TOKENS:
            terms.append(t)
    return terms


# id do setor → skills/termos característicos da área
SECTOR_SKILLS: dict[str, list[str]] = {
    "tec_all": [
        "python", "java", "javascript", "sql", "ti", "software", "dados",
        "cloud", "suporte", "desenvolvimento", "tecnologia",
    ],
    "tec_dev": [
        "python", "java", "javascript", "typescript", "php", "c#", ".net",
        "react", "node.js", "laravel", "api", "git",
    ],
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
    "emprego_geral": ["atendimento", "organização", "excel", "comunicação", "rotinas"],
    "varejo": ["atendimento", "vendas", "caixa", "estoque", "cliente"],
    "servicos": ["manutenção", "limpeza", "organização", "pontualidade"],
    "operacional": ["produção", "qualidade", "segurança", "equipe"],
    "primeiro_emprego": ["comunicação", "equipe", "aprendizado", "organização"],
    "limpeza": ["limpeza", "organização", "higiene"],
    "motorista": ["cnh", "direção", "entregas", "pontualidade"],
    "cozinha": ["higiene", "cozinha", "alimentos", "equipe"],
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
