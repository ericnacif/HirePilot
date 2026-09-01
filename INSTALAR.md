# Vaga em Vista — como instalar (Windows)

Guia para quem **não precisa** instalar Python nem usar terminal.

## 1. Baixar

1. Abra a página de **Releases** do projeto no GitHub.
2. Escolha um arquivo:
   - **`Vaga-em-Vista-Setup.exe`** — instalador (recomendado; cria atalho)
   - **`Vaga em Vista.exe`** — edição **Leve** (portátil, só APIs)
   - **`Vaga em Vista-Full.exe`** — edição **Completa** (LinkedIn/InfoJobs; na 1ª vez baixa o navegador)
   - **`Vaga-em-Vista-portable.zip`** — Leve + LEIA-ME.txt

## 2. Abrir no Windows

1. Dê **dois cliques** em `Vaga em Vista.exe`.
2. Antes de executar, abra **Propriedades → Assinaturas Digitais** e confirme o publicador.
3. Para a verificação mais forte, compare o SHA-256 do arquivo com `SHA256SUMS.txt` da release.
4. Se a assinatura estiver ausente ou inválida, **não execute** o arquivo e baixe-o novamente.

## 3. Usar

1. A janela do **Vaga em Vista** abre sozinha.
2. **Envie seu currículo** (PDF ou Word).
3. Escolha área/cargo e clique em **Buscar vagas**.
4. Abra as vagas que interessarem e use **Já apliquei** para acompanhar.

## O que funciona nesta versão

| Funciona | Observação |
|----------|------------|
| Gupy, Indeed, Greenhouse, Remotive, RemoteOK | Edição Leve e Completa |
| LinkedIn e InfoJobs | Só na edição **Completa** |
| Instalador com atalho | `Vaga-em-Vista-Setup.exe` |
| Upload, ATS, carta, alertas | Todas as edições |
| Atualização automática | O app avisa quando há versão nova no GitHub |

## Onde ficam seus dados

Tudo fica no seu PC, em:

`%LOCALAPPDATA%\HirePilot\data\`

Currículo enviado, favoritos e histórico **não vão para a nuvem**.

## Problemas comuns

**Não abre / fecha sozinho**  
- Instale o [WebView2](https://developer.microsoft.com/microsoft-edge/webview2/) (geralmente já vem no Windows 10/11).

**Antivírus bloqueou**  
- Confirme a assinatura digital e baixe novamente pelo link oficial do GitHub; não adicione exceções de antivírus.

**Nenhuma vaga**  
- Marque as fontes **Gupy** e **Remotive**, use **Busca ampla** e aumente **Máx. por fonte**.

## Fechar o app

Feche a janela do Vaga em Vista. Não precisa desinstalar nada.
