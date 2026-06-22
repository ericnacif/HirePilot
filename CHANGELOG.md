# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/).

## [1.5.0] - 2026-06-22

### Adicionado
- **Notificações de alertas** — desktop (Windows/macOS), Telegram, webhook e Notification API no navegador
- **Novas fontes** — CareerJet (API), Trabalha Brasil e Empregos.com.br
- **InfoJobs com sessão persistente** — contexto Playwright reutilizado entre buscas
- **Dedup visível** — badge «Também em» quando a mesma vaga aparece em vários portais
- **Score explicado** — botão «Por quê?» no card com detalhes ATS/match
- **Kanban drag-and-drop** — arraste cards entre colunas no pipeline
- **Vaga embutida** — painel inline de detalhes sem sair da lista
- **Repetir última busca** — botão no header e na área de busca
- **Preset «Só APIs»** — seleciona fontes sem navegador/login
- **Cache por fonte** — botão ↻ nos chips de fonte para invalidar e rebuscar
- **PIN web opcional** — `WEB_ACCESS_PIN` protege a interface em rede local
- **Testes** — dedupe rastreado e parser Empregos.com.br com fixture

### Alterado
- Vagas.com — seletores e scroll aprimorados
- Jooble/CareerJet marcados automaticamente quando a API key está no `.env`
- Health check das novas fontes no painel lateral

## [1.4.0] - 2026-06-22

### Adicionado
- **Assistente de conexão** — wizard para LinkedIn, Catho, Vagas.com e InfoJobs (login no navegador)
- **Status ao vivo por fonte** — painel durante a busca mostrando progresso de cada portal
- **Kanban de candidaturas** — aba Candidaturas com colunas Interesse → Candidatado → Entrevista → Oferta → Recusado
- **Catho com login** — sessão persistente + paginação para mais vagas além do preview
- **Onboarding Jooble** — hint na UI com link para cadastro da API key

### Alterado
- Filtro por fonte nos resultados (chips «Exibidas: Todas · Gupy · Catho…»)
- README atualizado com as 12 fontes suportadas

## [1.3.2] - 2026-06-22

### Adicionado
- Fontes **Catho** e **Vagas.com** via Playwright (contexto persistente)

## [1.2.0] - 2026-06-16

### Adicionado
- **Modo simples** — linguagem acessível, menos jargão técnico, fluxo enxuto para quem quer emprego rápido
- **Localização real** — cidade + UF com autocomplete (IBGE), filtro por cidade/estado/Brasil/remoto/exterior
- API `/api/locations/cities` e base `br_municipios.json` (5.570 municípios)
- Setores do dia a dia (varejo, operacional, primeiro emprego, etc.)

### Alterado
- Filtro de local **rigoroso** na cidade (ex.: Manhuaçu, MG não mistura com outras cidades)
- Indeed busca com cidade e estado formatados para o Brasil
- Mensagens quando não há vagas na região escolhida

## [1.1.5] - 2026-06-16

### Corrigido
- Release Windows: pasta `packaging/` local conflitava com a lib PyPI `packaging` exigida pelo PyInstaller (renomeada para `build_support/`)

## [1.1.4] - 2026-06-16

### Corrigido
- CI: lint Ruff no `runtime_hook_full.py`
- Executável: várias janelas ao abrir o Full (Playwright relançava o `.exe`)
- Executável: crash `PackageNotFoundError: werkzeug` no PyInstaller
- Instância única no Windows ao abrir o app duas vezes

### Alterado
- Specs PyInstaller renomeados para `hirepilot.spec` / `hirepilot-full.spec`
- Módulo compartilhado `build_support/pyinstaller_common.py`
- Release workflow roda lint e testes antes do build Windows

## [1.1.3] - 2026-06-16

### Corrigido
- Mesmas correções críticas do executável (primeira tag com fix do Full)

## [1.1.2] - 2026-06-16

### Alterado
- Logo e wordmark oficiais (PNG)
- Repositório GitHub renomeado para **HirePilot**
- CLI principal `hirepilot` (alias `vagamatch`)
- Migração automática de dados `VagaMatch` → `HirePilot`
- Migração de `localStorage` no navegador

## [1.1.0] - 2026-06

### Adicionado
- Instalador Inno Setup, splash, onboarding, dois builds (Leve/Full)
- Verificação de atualização via GitHub Releases

## [1.0.0] - 2026-06

### Adicionado
- Primeiro release público com `.exe` Windows
