# HirePilot — como instalar (Windows)

Guia para quem **não precisa** instalar Python nem usar terminal.

## 1. Baixar

1. Abra a página de **Releases** do projeto no GitHub.
2. Escolha um arquivo:
   - **`HirePilot-Setup.exe`** — instalador (recomendado; cria atalho)
   - **`HirePilot.exe`** — edição **Leve** (portátil, só APIs)
   - **`HirePilot-Full.exe`** — edição **Completa** (LinkedIn/InfoJobs; na 1ª vez baixa o navegador)
   - **`HirePilot-portable.zip`** — Leve + LEIA-ME.txt

## 2. Abrir no Windows

1. Dê **dois cliques** em `HirePilot.exe`.
2. Se o Windows mostrar *"O Windows protegeu seu PC"*:
   - Clique em **Mais informações**
   - Depois em **Executar assim mesmo**  
   *(o app não tem certificado pago da Microsoft — isso é normal em apps independentes)*

## 3. Usar

1. A janela do **HirePilot** abre sozinha.
2. **Envie seu currículo** (PDF ou Word).
3. Escolha área/cargo e clique em **Buscar vagas**.
4. Abra as vagas que interessarem e use **Já apliquei** para acompanhar.

## O que funciona nesta versão

| Funciona | Observação |
|----------|------------|
| Gupy, Indeed, Greenhouse, Remotive, RemoteOK | Edição Leve e Completa |
| LinkedIn e InfoJobs | Só na edição **Completa** |
| Instalador com atalho | `HirePilot-Setup.exe` |
| Upload, ATS, carta, alertas | Todas as edições |
| Atualização automática | O app avisa quando há versão nova no GitHub |

## Onde ficam seus dados

Tudo fica no seu PC, em:

`%LOCALAPPDATA%\VagaMatch\data\`

Currículo enviado, favoritos e histórico **não vão para a nuvem**.

## Problemas comuns

**Não abre / fecha sozinho**  
- Instale o [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/) (geralmente já vem no Windows 10/11).

**Antivírus bloqueou**  
- Adicione exceção para `HirePilot.exe` ou baixe de novo pelo link oficial do GitHub.

**Nenhuma vaga**  
- Marque as fontes **Gupy** e **Remotive**, use **Busca ampla** e aumente **Máx. por fonte**.

## Fechar o app

Feche a janela do HirePilot. Não precisa desinstalar nada.
