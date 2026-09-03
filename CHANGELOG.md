# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/).

## [Não lançado]

### Alterado
- Rebranding do aplicativo para **Vaga em Vista** na interface, documentação,
  comandos, armazenamento local e assets de distribuição.
- Dados existentes em `HirePilot`, `.hirepilot`, `VagaMatch` e `.vagamatch`
  são migrados automaticamente para a nova pasta do aplicativo.
- Os comandos `hirepilot` e `vagamatch` permanecem disponíveis como aliases de
  compatibilidade; o comando preferencial passa a ser `vaga-em-vista`.

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
