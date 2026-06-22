# HirePilot

> **HirePilot** — seu copiloto inteligente para conquistar a vaga ideal.

[![CI](https://github.com/ericnacif/HirePilot/actions/workflows/ci.yml/badge.svg)](https://github.com/ericnacif/HirePilot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)

## Início rápido (2 minutos)

| Quem é você? | O que fazer |
|--------------|-------------|
| **Quero só usar** (sem Python) | Baixe o `.exe` na página [Releases](https://github.com/ericnacif/HirePilot/releases) e siga o [INSTALAR.md](INSTALAR.md) — duplo clique, envie o CV, busque vagas. |
| **Desenvolvedor** | `pip install -e .` → `playwright install chromium` → `python run_app.py` (janela desktop) ou `hirepilot web` (navegador). |
| **Docker** | `docker compose up --build` → acesse `http://localhost:5000`. |

> **Uso local/privado:** a interface web guarda currículos em `data/uploads/` no seu PC. Não hospede publicamente na internet sem autenticação — foi pensada para uso pessoal ou em rede privada.

Detalhes técnicos, CLI, filtros e aviso legal continuam abaixo.

---

Aplicação Python que lê seu currículo, busca vagas em **várias plataformas** (Gupy, Indeed, Sólides, Trampos, Catho, Vagas.com, InfoJobs, LinkedIn, Jooble, CareerJet, Trabalha Brasil, Empregos.com.br, Remotive, RemoteOK, Greenhouse), ranqueia por compatibilidade com matching semântico **gratuito/local**, analisa compatibilidade **ATS**, gera **carta de apresentação** (PT/EN) e prepara candidaturas — **você confirma o envio manualmente**.

Tem uma **interface web reutilizável** (qualquer pessoa sobe o próprio currículo) e uma **CLI** completa.

## Plataformas suportadas

| Fonte | Como funciona | Login | Candidatura |
|-------|---------------|-------|-------------|
| `gupy` | API pública | Não | Link manual |
| `indeed` | RSS Brasil | Não | Link manual |
| `solides` | API pública (vagas.solides.com.br) | Não | Link manual |
| `trampos` | API pública (trampos.co) | Não | Link manual |
| `catho` | Navegador (Playwright, sessão persistente) | Opcional (mais vagas) | Link manual |
| `vagascom` | Navegador (Playwright) | Manual (1ª vez) | Link manual |
| `trabalhabrasil` | Navegador (Playwright) | Não | Link manual |
| `empregoscom` | Scraping HTTP leve | Não | Link manual |
| `jooble` | API agregadora (requer `JOOBLE_API_KEY`) | Não | Link externo |
| `careerjet` | API agregadora (requer `CAREERJET_API_KEY`) | Não | Link externo |
| `infojobs` | Navegador (Playwright, sessão persistente) | Opcional | Link manual |
| `linkedin` | Navegador (Playwright) | Manual (1ª vez) | Easy Apply assistido |
| `greenhouse` | API pública (boards US) | Não | Link manual |
| `remotive` | API pública (só remoto) | Não | Link manual |
| `remoteok` | API pública (só remoto) | Não | Link manual |

As APIs públicas (Gupy, Sólides, Trampos, Empregos.com.br, Remotive, RemoteOK, Indeed) são as mais estáveis. Catho, Vagas.com, LinkedIn, InfoJobs e Trabalha Brasil abrem o navegador — use o **assistente de conexão** na interface na 1ª busca.

**v1.5** traz alertas com notificação (desktop/Telegram/webhook), dedup visível, kanban com drag-and-drop, preset «Só APIs», repetir última busca, PIN web opcional (`WEB_ACCESS_PIN`) e cache por fonte.

## Aviso legal

O LinkedIn proíbe automação e scraping nos [Termos de Uso](https://www.linkedin.com/legal/user-agreement). Este projeto opera em **modo assistido**:

- Navegador visível (não headless por padrão)
- Login manual na primeira vez (sessão salva em `browser_data/`)
- Pré-preenchimento de campos quando possível
- **O clique final em "Enviar candidatura" é sempre seu**
- Delays humanos e limite diário configurável

Use por sua conta e risco. Não há garantia contra bloqueio de conta.

## Requisitos

- Python 3.10+
- Conta LinkedIn
- Currículo em PDF ou DOCX

## Instalação

```bash
# Clone o repositório
git clone https://github.com/ericnacif/HirePilot.git
cd HirePilot

# Ambiente virtual (recomendado)
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# Opção A: instalar como pacote (cria o comando `hirepilot`; `vagamatch` continua como alias)
pip install -e .
# Opção B: só as dependências
pip install -r requirements.txt

# Navegador para LinkedIn/InfoJobs (opcional se usar só as APIs)
playwright install chromium
```

Com a instalação via `pip install -e .`, use `hirepilot` no lugar de `python -m cv_apply` (ex.: `hirepilot web`). O comando `vagamatch` ainda funciona.

### Docker (rodar com um comando)

A forma mais rápida de subir a interface web, sem instalar nada além do Docker:

```bash
docker compose up --build
```

Acesse `http://localhost:5000`. **Use só na sua máquina ou rede privada** — a imagem não inclui autenticação; uploads ficam no volume `hirepilot-data`.

A imagem é enxuta (sem Playwright/torch): as fontes
via API (Gupy, Remotive, RemoteOK) e o matching por palavras-chave funcionam normalmente.
As fontes LinkedIn/InfoJobs (que abrem navegador) e o matching semântico ficam
desativados nesse modo. Os dados (uploads) ficam no volume `hirepilot-data`.

Sem o compose:

```bash
docker build -t hirepilot .
docker run -p 5000:5000 -v hirepilot-data:/app/data hirepilot
```

### App desktop — executável Windows (.exe)

Para quem **não tem Python** instalado: um único `HirePilot.exe` que abre **uma janela
nativa do app** (sem terminal preto e sem abrir o Chrome separado).

**Gerar o executável** (só quem desenvolve, uma vez):

```bat
build_exe.bat
```

O arquivo sai em `dist\HirePilot.exe`.

**Usar o executável:**

1. Duplo clique em `HirePilot.exe`
2. Abre a janela do HirePilot com a interface dentro
3. Feche a janela para encerrar

**O que vem no .exe (versão leve):**

| Recurso | No .exe |
|---------|---------|
| Interface web, upload, ATS, carta, adaptar currículo | Sim |
| Fontes Gupy, Indeed, Remotive, RemoteOK | Sim |
| LinkedIn / InfoJobs (navegador) | Não |
| Matching semântico (torch) | Não — usa TF-IDF local |

Dados em `%LOCALAPPDATA%\HirePilot\data\`. Requer **WebView2** (padrão no Windows 10/11).

### Distribuir para um amigo (sem código)

1. Publique um release (build do `.exe`, instalador e ZIP **automáticos** no GitHub Actions):

```bash
git tag v1.2.1
git push origin v1.2.1
```

O workflow [release.yml](.github/workflows/release.yml) roda testes, gera os executáveis Windows e publica na página **Releases** (notas geradas pelo Release Drafter).

Repositório: https://github.com/ericnacif/HirePilot

2. Na página **Releases**, envie ao amigo:
   - **`HirePilot-Setup.exe`** — instalador (melhor opção)
   - ou **`HirePilot-portable.zip`** — versão portátil

Arquivos no release: Leve (`HirePilot.exe`), Completa (`HirePilot-Full.exe`), instalador e ZIP.  
Instruções para leigos: [INSTALAR.md](INSTALAR.md). Histórico: [CHANGELOG.md](CHANGELOG.md).

**Testar o modo app sem gerar o .exe:**

```bash
pip install -r requirements-web.txt
python run_app.py
```

Para forçar abertura no navegador (debug): `set HIREPILOT_BROWSER=1` e rode `python run_app.py`.

### Desenvolvimento

```bash
pip install -e ".[dev]"   # inclui pytest e ruff
pytest                     # roda os testes
ruff check .               # lint
```

## Configuração

Copie o arquivo de exemplo e ajuste:

```bash
cp .env.example .env
```

Principais variáveis:

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `RESUME_PATH` | Caminho do currículo | `meu_cv.pdf` |
| `SEARCH_KEYWORDS` | Palavras-chave da busca | `desenvolvedor python` |
| `SEARCH_LOCATION` | Localização | `Brasil` |
| `SEARCH_SOURCES` | Fontes (vírgula): ver tabela acima | `gupy,solides,trampos,catho` |
| `JOOBLE_API_KEY` | Chave Jooble (agregador BR/internacional) | vazio |
| `SEARCH_WORKPLACE` | `remoto`, `hibrido`, `presencial` (vírgula) | vazio (qualquer) |
| `SEARCH_JOB_TYPE` | `efetivo`, `estagio`, `meio_periodo`, `temporario`, `pj` | vazio |
| `SEARCH_EXPERIENCE` | `estagio`, `junior`, `pleno`, `senior`, `diretor`, `executivo` | vazio |
| `SEARCH_DATE_POSTED` | `24h`, `semana`, `mes`, `qualquer` | `qualquer` |
| `MIN_MATCH_SCORE` | Score mínimo (0-100) | `60` |
| `DAILY_APPLY_LIMIT` | Limite diário de vagas | `10` |
| `USE_SEMANTIC_MATCHING` | Usar sentence-transformers | `true` |
| `LLM_PROVIDER` | `none`, `ollama` ou `groq` | `none` |
| `MAX_UPLOAD_MB` | Tamanho máximo do currículo (web) | `8` |
| `RATE_LIMIT_MAX` | Máx. de requisições à API por minuto (web) | `30` |
| `SEARCH_RATE_MAX` | Máx. de buscas por minuto (web) | `8` |

### Filtros e fontes

Os filtros valem para todas as fontes (quando a plataforma suporta). Exemplos:

```bash
# Buscar só na Gupy e InfoJobs, vagas de estágio
SEARCH_SOURCES=gupy,infojobs
SEARCH_JOB_TYPE=estagio

# Remoto e híbrido, publicadas na última semana
SEARCH_WORKPLACE=remoto,hibrido
SEARCH_DATE_POSTED=semana
```

Também dá pra escolher as fontes direto no comando:

```bash
python -m cv_apply search --sources gupy,remotive --limit 10
```

Coloque seu currículo na raiz do projeto (ex.: `meu_cv.pdf`) ou informe o caminho em `RESUME_PATH`.

## Uso

### Interface web (mais fácil, reutilizável)

```bash
python -m cv_apply web
```

Abre no navegador a interface **HirePilot** que **qualquer pessoa** pode usar — cada um tem sua sessão isolada, sem precisar de conta:

1. **Sobe o currículo** (PDF/DOCX) na tela inicial
2. Recebe na hora o **perfil extraído** e a **nota ATS de formato** (anel de score)
3. Preenche setor/cargo, localização e filtra por modelo de trabalho, tipo, nível e data
4. Escolhe as fontes (Gupy, Indeed, Remotive, RemoteOK por padrão; InfoJobs/LinkedIn abrem navegador)
5. Vê as vagas **ordenadas por compatibilidade**, com barras de **match** e **ATS**
6. Em cada vaga: **Aplicar**, **Análise ATS**, **Adaptar currículo**, **Carta** e **Já apliquei** (marca manualmente)
7. **Alertas** de vagas novas (web e desktop, a cada 30 min) e **busca sem cache**

Qualidade da busca (uniforme em todas as fontes):

- **Palavra-chave tem prioridade**: se você digita `php`, a busca traz vagas de PHP
  (o setor não dilui mais o termo); o setor entra como busca só quando não há
  palavras-chave e sempre influencia o ranqueamento.
- **Filtro real de senioridade**: o nível (júnior/pleno/sênior) é aplicado a Gupy,
  Remotive e RemoteOK também — pedir júnior não traz mais vagas sênior.
- **Filtro de relevância**: vagas que não mencionam o termo/área buscada são
  removidas, em vez de devolver resultados aleatórios.

Outros recursos da interface: **seletor de setor/área** (com palavras-chave opcionais)
que sugere a área a partir do currículo e ainda **prioriza no ranqueamento** as vagas
com skills daquela área; **status por fonte** (quantas vagas cada plataforma retornou)
e **health check proativo** (qual fonte está OK, instável ou indisponível antes da busca);
estado vazio inteligente; tema claro/escuro, paginação e ordenação dos resultados,
buscas salvas, exportação (CSV/JSON) e reconhecimento de **sinônimos de skills**
(ex.: `js`→`javascript`, `k8s`→`kubernetes`).

> **Privacidade:** ao rodar `hirepilot web`, se a porta 5000 já estiver ocupada por um servidor
> anterior, ela é liberada automaticamente (use `--keep-port` para desativar).
> Currículos enviados vão para `data/uploads/` no disco local — **não use em servidor público** sem proteger o acesso.

Não precisa configurar nada antes — o currículo é enviado pela própria interface.

> Os dados de cada pessoa ficam só na sessão dela (em memória) e o arquivo enviado vai para `data/uploads/`.

### Linha de comando

### 1. Extrair perfil do currículo

```bash
python -m cv_apply parse meu_cv.pdf
```

Mostra nome, skills, senioridade e salva em `data/profile.json`.

### 2. Buscar vagas

```bash
python -m cv_apply search
```

Busca nas fontes definidas em `SEARCH_SOURCES` e salva em `data/cv_apply.db`. Se `linkedin` estiver na lista, abre o Chromium e pede login na primeira vez. As demais fontes (Gupy, Remotive, RemoteOK) usam API e não precisam de login.

```bash
# Só APIs (rápido, sem navegador)
python -m cv_apply search --sources gupy,remotive,remoteok --limit 15
```

### 3. Ranquear por compatibilidade

```bash
python -m cv_apply rank
```

Calcula score 0-100 usando:

- Similaridade semântica local (`all-MiniLM-L6-v2`) ou TF-IDF como fallback
- Overlap de skills
- Compatibilidade de senioridade e localização

Exporta `data/rankings.json`.

### 3a. Análise ATS do currículo

```bash
python -m cv_apply ats --limit 5
```

Analisa seu currículo contra as vagas top e mostra:

- **Checagem de formato ATS**: email/telefone, seções essenciais (experiência, formação, habilidades), tamanho, texto extraível (detecta currículo em imagem) e excesso de imagens
- **Score ATS por vaga**: cobertura de palavras-chave da vaga (0-100)
- **Palavras-chave faltando** em cada vaga e um agregado do que mais falta no geral

Tudo local, sem LLM. Use pra saber o que ajustar no seu currículo.

### 3b. Currículo adaptado + carta por vaga

```bash
python -m cv_apply tailor --limit 3
```

Gera em `data/tailored/` para cada vaga top:

- `*.md` — currículo adaptado (rascunho): resumo direcionado, skills relevantes priorizadas, checklist de palavras-chave a incluir e sugestões ATS
- `*_carta.txt` — carta de apresentação personalizada com as skills que batem com a vaga

> São **rascunhos** baseados em palavras-chave para você revisar — não reescrevem seu PDF automaticamente. Com LLM grátis ligado (Ollama/Groq), a carta fica ainda mais sob medida.

#### Vagas internacionais e currículos em inglês

- Currículos em inglês são lidos normalmente (skills, senioridade, anos de experiência, resumo).
- Fontes internacionais: **Remotive** e **RemoteOK** (remoto global) e **LinkedIn** com a localização ajustada (ex.: "Portugal", "United States", "Remote").
- A **carta de apresentação** se adapta ao idioma: por padrão (`COVER_LETTER_LANG=auto`) detecta o idioma da vaga e escreve em inglês para vagas em inglês. Dá para forçar com `COVER_LETTER_LANG=pt` ou `en`, e na interface web há botões **Auto / Português / English** no modal da carta.

### 4. Preparar candidaturas (modo assistido)

```bash
python -m cv_apply apply
```

Vagas do **LinkedIn** com Easy Apply (modo assistido):

1. Abre a vaga no LinkedIn
2. Clica em Easy Apply
3. Pré-preenche textareas e anexa currículo quando possível
4. **Para antes de enviar** — você revisa e clica Enviar
5. Pressiona ENTER no terminal para seguir para a próxima

Vagas de **outras plataformas** (Gupy, InfoJobs, Remotive, RemoteOK) não têm Easy Apply. Use `--no-easy-only` para listá-las como candidatura manual (mostra o link, com opção de abrir no navegador):

```bash
# LinkedIn assistido + links das outras plataformas
python -m cv_apply apply --no-easy-only --open-browser

# Só as melhores, com carta sugerida
python -m cv_apply apply --min-score 70 --limit 5 --show-letter
```

## LLM gratuito (opcional)

Por padrão, a carta de apresentação usa template Jinja2 (sem custo).

### Ollama (local, grátis)

1. Instale [Ollama](https://ollama.com/)
2. `ollama pull llama3.2`
3. No `.env`: `LLM_PROVIDER=ollama`

### Groq (API free tier)

1. Crie conta em [console.groq.com](https://console.groq.com/)
2. No `.env`:
   ```
   LLM_PROVIDER=groq
   GROQ_API_KEY=sua_chave
   ```

## Estrutura do projeto

```
eric/
├── cv_apply/
│   ├── cli.py              # Comandos parse/search/rank/ats/tailor/apply/web
│   ├── webapp.py           # Interface web (Flask)
│   ├── config.py           # Configurações (.env)
│   ├── profile.py          # Modelos CandidateProfile, JobPosting
│   ├── resume_parser.py    # Leitura PDF/DOCX
│   ├── matching.py         # Matching semântico + keywords
│   ├── filters.py          # Filtros (workplace, tipo, nível, data)
│   ├── sources.py          # Fontes: LinkedIn, Gupy, InfoJobs, Remotive, RemoteOK
│   ├── linkedin.py         # Playwright (busca + Easy Apply)
│   ├── ats.py              # Análise ATS (cobertura + formato)
│   ├── tailor.py           # Currículo adaptado por vaga
│   ├── cover_letter.py     # Carta por template ou LLM
│   ├── storage.py          # SQLite + JSON
│   └── skills_dict.py      # Dicionário de skills
├── data/                   # Perfil, vagas, rankings, tailored/ (gerado)
├── browser_data/           # Sessão do navegador (gerado)
├── requirements.txt
├── .env.example
└── README.md
```

## Fluxo

```
Currículo → parse → perfil
                    ↓
              search (várias fontes) → vagas
                    ↓
              rank → top N compatíveis
                    ↓
        ats / tailor → análise ATS + currículo e carta adaptados
                    ↓
              apply (assistido) → você envia
```

## Solução de problemas

**Nenhuma vaga encontrada:** O LinkedIn muda seletores com frequência. Ajuste em `cv_apply/linkedin.py`.

**Modelo semântico lento na primeira vez:** O `sentence-transformers` baixa ~90MB na primeira execução. Use `USE_SEMANTIC_MATCHING=false` para só TF-IDF.

**Login não detectado:** Faça login manualmente na janela do Chromium e aguarde. A sessão fica em `browser_data/`.

**Bloqueio / captcha:** Reduza `DAILY_APPLY_LIMIT`, aumente pausas entre sessões e evite uso excessivo.

## Licença

Uso educacional/pessoal. Respeite os Termos de Uso do LinkedIn e das plataformas de emprego.
