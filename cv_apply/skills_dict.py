"""Dicionário de skills técnicas para extração do currículo."""

from __future__ import annotations

import re
from functools import lru_cache

SKILLS_DICTIONARY: list[str] = [
    # Linguagens
    "python", "javascript", "typescript", "java", "c#", "c++", "c",
    "go", "golang", "rust", "ruby", "php", "swift", "kotlin", "scala",
    "r", "matlab", "dart", "objective-c", "perl", "elixir", "clojure",
    "groovy", "lua", "bash", "shell script", "powershell", "vba",
    # Web frontend
    "html", "html5", "css", "css3", "sass", "scss", "less", "tailwind",
    "tailwind css", "bootstrap", "material ui", "styled-components",
    "react", "react native", "vue", "vue.js", "angular", "angularjs",
    "next.js", "nextjs", "nuxt", "svelte", "remix", "jquery", "redux",
    "webpack", "vite", "babel",
    # Web backend / frameworks
    "node.js", "nodejs", "express", "nestjs", "django", "flask", "fastapi",
    "spring", "spring boot", "laravel", "symfony", "codeigniter", "rails",
    "ruby on rails", "asp.net", ".net", ".net core", "dotnet", "phoenix",
    "fiber", "gin", "quarkus", "micronaut",
    # Dados / ML / BI
    "sql", "nosql", "postgresql", "postgres", "mysql", "mariadb",
    "sql server", "oracle", "sqlite", "mongodb", "redis", "elasticsearch",
    "cassandra", "dynamodb", "firebase", "firestore", "supabase",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "machine learning", "deep learning", "data science", "spark",
    "hadoop", "kafka", "airflow", "databricks", "snowflake", "dbt",
    "power bi", "tableau", "looker", "etl", "data engineering",
    "nlp", "computer vision", "llm", "langchain", "openai",
    # DevOps / Cloud / Infra
    "docker", "kubernetes", "k8s", "aws", "azure", "gcp",
    "google cloud", "terraform", "ansible", "pulumi", "jenkins",
    "gitlab ci", "github actions", "circleci", "travis", "argocd",
    "ci/cd", "linux", "unix", "nginx", "apache", "rabbitmq",
    "prometheus", "grafana", "datadog", "cloudflare", "vercel",
    "netlify", "heroku", "serverless", "lambda", "ec2", "s3",
    # Mobile
    "android", "ios", "flutter", "xamarin", "ionic", "jetpack compose",
    # Arquitetura / práticas
    "agile", "scrum", "kanban", "rest", "rest api", "restful", "graphql",
    "grpc", "soap", "microservices", "microsserviços", "monolito",
    "api", "apis", "soa", "ddd", "tdd", "bdd", "solid", "clean code",
    "clean architecture", "design patterns", "mvc", "mvvm",
    "event-driven", "message queue", "websocket", "oauth", "jwt",
    "backend", "frontend", "full stack", "fullstack", "devops", "sre",
    # QA / testes
    "qa", "testes", "teste", "qualidade", "automação", "automation",
    "selenium", "playwright", "cypress", "jest", "vitest", "pytest",
    "junit", "mocha", "jasmine", "karma", "testng", "cucumber",
    "unit testing", "teste unitário", "teste de integração",
    "teste automatizado",
    # Ferramentas
    "git", "github", "gitlab", "bitbucket", "jira", "confluence",
    "figma", "postman", "insomnia", "swagger", "openapi", "trello",
    "notion", "slack", "vs code",
    # Português / áreas
    "desenvolvimento", "programação", "banco de dados",
    "inteligência artificial", "análise de dados", "ciência de dados",
    "engenharia de software", "arquitetura de software",
    "integração de sistemas", "versionamento", "metodologias ágeis",
]

SENIORITY_KEYWORDS: dict[str, list[str]] = {
    "estagiário": ["estagiário", "estagiaria", "estágio", "intern", "trainee"],
    "júnior": ["júnior", "junior", "jr", "entry level", "iniciante"],
    "pleno": ["pleno", "mid", "mid-level", "intermediário", "intermediario"],
    "sênior": ["sênior", "senior", "sr", "lead", "principal", "staff"],
}

JOB_TITLE_PATTERNS: list[str] = [
    "desenvolvedor", "developer", "engenheiro", "engineer", "analista",
    "arquiteto", "architect", "programador", "cientista", "scientist",
    "tech lead", "gerente", "manager", "consultor", "consultant",
    "devops", "sre", "qa", "tester", "designer", "product owner",
    "scrum master", "data analyst", "data engineer",
]


# Borda própria para tokens de skill. ``\b`` do regex falha em skills que
# começam/terminam com símbolos (ex.: "c++", "c#", ".net") — esses nunca eram
# detectados. As bordas abaixo:
#   - casam "c++", "c#", ".net" mesmo seguidos de pontuação ("C++." no fim da frase);
#   - evitam "c" casar dentro de "c++" / "c#";
#   - evitam ".net" casar dentro de "asp.net".
# À direita, bloqueamos apenas continuação de "token de código" (letras, dígitos,
# ``+`` e ``#``), permitindo ``.`` e ``,`` de pontuação.
_RIGHT_BOUNDARY = r"(?![a-z0-9+#])"


def skill_pattern(skill: str) -> str:
    """Regex (string) que casa ``skill`` como token isolado, símbolos incluídos."""
    s = skill.lower()
    escaped = re.escape(s)
    if s[0].isalnum():
        left = r"(?<![a-z0-9+#./\-])"
    else:
        # skill começa com símbolo (ex.: ".net"): basta não vir colado em alfanumérico
        left = r"(?<![a-z0-9])"
    return left + escaped + _RIGHT_BOUNDARY


@lru_cache(maxsize=2048)
def compile_skill_regex(skill: str) -> re.Pattern[str]:
    return re.compile(skill_pattern(skill))


# Pré-compilado uma vez: usado em extração de currículo, matching e ATS.
SKILL_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    (skill, compile_skill_regex(skill)) for skill in SKILLS_DICTIONARY
]


def find_skills(text: str) -> list[str]:
    """Retorna as skills do dicionário presentes em ``text`` (ordenadas)."""
    lowered = (text or "").lower()
    found = [skill for skill, rx in SKILL_REGEXES if rx.search(lowered)]
    return sorted(set(found), key=str.lower)
