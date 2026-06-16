# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/).

## [1.1.4] - 2026-06-16

### Corrigido
- CI: lint Ruff no `runtime_hook_full.py`
- Executável: várias janelas ao abrir o Full (Playwright relançava o `.exe`)
- Executável: crash `PackageNotFoundError: werkzeug` no PyInstaller
- Instância única no Windows ao abrir o app duas vezes

### Alterado
- Specs PyInstaller renomeados para `hirepilot.spec` / `hirepilot-full.spec`
- Módulo compartilhado `packaging/pyinstaller_common.py`
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
