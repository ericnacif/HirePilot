"""Interface de linha de comando."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cv_apply.ats import aggregate_missing_keywords, analyze_ats
from cv_apply.config import get_settings
from cv_apply.cover_letter import generate_cover_letter
from cv_apply.filters import SearchFilters
from cv_apply.linkedin import LinkedInClient
from cv_apply.matching import rank_jobs
from cv_apply.resume_parser import parse_resume
from cv_apply.sources import AVAILABLE_SOURCES, dedupe_jobs, run_sources
from cv_apply.storage import Storage
from cv_apply.tailor import save_tailored_resume

console = Console()
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def cmd_parse(args: argparse.Namespace) -> int:
    settings = get_settings()
    path = Path(args.resume) if args.resume else settings.resume_path

    try:
        profile = parse_resume(path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Erro:[/red] {exc}")
        return 1

    storage = Storage(settings.data_dir)
    storage.save_profile(profile)

    table = Table(title=f"Perfil extraído de {path.name}")
    table.add_column("Campo", style="cyan")
    table.add_column("Valor")

    table.add_row("Nome", profile.name or "-")
    table.add_row("E-mail", profile.email or "-")
    table.add_row("Telefone", profile.phone or "-")
    table.add_row("Senioridade", profile.seniority or "-")
    table.add_row("Anos exp.", str(profile.years_experience or "-"))
    table.add_row("Skills", ", ".join(profile.skills) or "-")
    table.add_row("Cargos", ", ".join(profile.job_titles[:3]) or "-")
    table.add_row("Locais", ", ".join(profile.locations) or "-")

    console.print(table)
    console.print(f"\n[green]Perfil salvo em[/green] {settings.data_dir / 'profile.json'}")
    return 0


def _load_profile(storage: Storage, settings):
    profile = storage.load_profile()
    if profile:
        return profile
    if settings.resume_path.exists():
        profile = parse_resume(settings.resume_path)
        storage.save_profile(profile)
        return profile
    console.print(
        "[red]Nenhum perfil encontrado.[/red] Execute: python -m cv_apply parse seu_cv.pdf"
    )
    return None


def cmd_search(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = Storage(settings.data_dir)

    if args.sources:
        settings.search_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    invalid = [s for s in settings.search_sources if s not in AVAILABLE_SOURCES]
    if invalid:
        console.print(f"[red]Fonte(s) inválida(s):[/red] {', '.join(invalid)}")
        console.print(f"Disponíveis: {', '.join(AVAILABLE_SOURCES)}")
        return 1

    max_jobs = args.limit or settings.top_jobs_to_show
    filters = SearchFilters.from_settings(settings)

    info = (
        f"Fontes: [cyan]{', '.join(settings.search_sources)}[/cyan]\n"
        f"Busca: [cyan]{filters.keywords}[/cyan] | Local: [cyan]{filters.location}[/cyan]\n"
        f"Workplace: {', '.join(filters.workplace) or 'qualquer'} | "
        f"Tipo: {', '.join(filters.job_type) or 'qualquer'} | "
        f"Nível: {', '.join(filters.experience) or 'qualquer'} | "
        f"Data: {filters.date_posted}"
    )
    if "linkedin" in settings.search_sources:
        info += "\n[yellow]LinkedIn:[/yellow] abrirá o navegador para login assistido."
    console.print(Panel(info, title="Busca de vagas"))

    results = run_sources(
        settings,
        max_jobs=max_jobs,
        on_log=lambda m: console.print(f"[dim]{m}[/dim]"),
    )

    all_jobs = []
    for jobs in results.values():
        all_jobs.extend(jobs)

    if not all_jobs:
        console.print("[yellow]Nenhuma vaga encontrada.[/yellow]")
        return 0

    raw_count = len(all_jobs)
    all_jobs = dedupe_jobs(all_jobs)
    removed = raw_count - len(all_jobs)

    storage.save_jobs(all_jobs)
    msg = f"\n[green]{len(all_jobs)} vagas salvas[/green] em {settings.data_dir}"
    if removed:
        msg += f" [dim]({removed} duplicada(s) removida(s))[/dim]"
    console.print(msg)

    table = Table(title="Vagas encontradas (resumo por fonte)")
    table.add_column("Fonte", style="cyan")
    table.add_column("Qtd", justify="right")
    for name, jobs in results.items():
        table.add_row(name, str(len(jobs)))
    console.print(table)

    sample = Table(title="Amostra de vagas")
    sample.add_column("#", style="dim")
    sample.add_column("Título")
    sample.add_column("Empresa")
    sample.add_column("Local")
    for i, job in enumerate(all_jobs[:15], 1):
        sample.add_row(str(i), job.title[:45], job.company[:25], (job.location or "-")[:25])
    console.print(sample)
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = Storage(settings.data_dir)

    profile = _load_profile(storage, settings)
    if not profile:
        return 1

    jobs = storage.load_jobs()
    if not jobs:
        console.print("[red]Nenhuma vaga salva.[/red] Execute: python -m cv_apply search")
        return 1

    min_score = args.min_score if args.min_score is not None else settings.min_match_score
    matches = rank_jobs(
        profile,
        jobs,
        min_score=min_score,
        use_semantic=settings.use_semantic_matching,
    )

    limit = args.limit or settings.top_jobs_to_show
    matches = matches[:limit]
    storage.save_rankings(matches)
    out_path = storage.export_rankings_json(matches)
    if getattr(args, "csv", False):
        csv_path = storage.export_rankings_csv(matches)

    table = Table(title=f"Top {len(matches)} vagas (score >= {min_score})")
    table.add_column("#", style="dim")
    table.add_column("Score", style="bold green")
    table.add_column("Vaga")
    table.add_column("Empresa")
    table.add_column("Motivos")

    for i, match in enumerate(matches, 1):
        reasons = "; ".join(match.reasons[:2])
        table.add_row(
            str(i),
            f"{match.score:.0f}",
            match.job.title[:40],
            match.job.company[:25],
            reasons[:60],
        )

    console.print(table)
    console.print(f"\n[green]Ranking exportado:[/green] {out_path}")
    if getattr(args, "csv", False):
        console.print(f"[green]CSV exportado:[/green] {csv_path}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = Storage(settings.data_dir)

    profile = _load_profile(storage, settings)
    if not profile:
        return 1

    ranked = storage.load_latest_rankings()
    if not ranked:
        console.print("[red]Nenhum ranking.[/red] Execute: python -m cv_apply rank")
        return 1

    min_score = args.min_score if args.min_score is not None else settings.min_match_score
    ranked = [(j, m) for j, m in ranked if m.score >= min_score]

    if not ranked:
        console.print(f"[yellow]Nenhuma vaga com score >= {min_score}.[/yellow]")
        return 0

    daily_limit = settings.daily_apply_limit
    already_today = storage.applications_today_count()
    remaining = max(0, daily_limit - already_today)

    if remaining == 0:
        console.print(
            f"[yellow]Limite diário atingido ({daily_limit}). "
            "Ajuste DAILY_APPLY_LIMIT no .env[/yellow]"
        )
        return 0

    to_apply = ranked[: min(args.limit or remaining, remaining)]
    to_apply = [(j, m) for j, m in to_apply if not storage.has_applied(j.id)]

    if not to_apply:
        console.print("[yellow]Nenhuma vaga nova para candidatar no ranking.[/yellow]")
        return 0

    # LinkedIn Easy Apply é automatizável; outras fontes são candidatura manual
    linkedin_jobs = [(j, m) for j, m in to_apply if j.easy_apply and "linkedin.com" in j.url]
    manual_jobs = [(j, m) for j, m in to_apply if (j, m) not in linkedin_jobs]

    console.print(Panel(
        f"LinkedIn (assistido): {len(linkedin_jobs)} | "
        f"Outras plataformas (manual): {len(manual_jobs)}",
        title="Apply",
    ))

    applied = 0

    # Candidaturas manuais (Gupy, InfoJobs, Remotive, RemoteOK): abre o link
    if manual_jobs and not args.easy_only:
        import webbrowser

        console.print("\n[bold]Candidaturas manuais[/bold] (abra o link e candidate-se no site):")
        for job, match in manual_jobs:
            console.print(f"\n[bold]>>> {job.title}[/bold] @ {job.company} (score {match.score:.0f})")
            console.print(f"  Link: [link]{job.url}[/link]")
            if args.show_letter:
                letter = generate_cover_letter(profile, job, settings)
                console.print(Panel(letter, title="Carta sugerida"))
            if args.open_browser:
                try:
                    webbrowser.open(job.url)
                except Exception:
                    pass
            storage.record_application(job, status="manual")
            applied += 1
    elif manual_jobs:
        console.print(
            f"\n[dim]{len(manual_jobs)} vaga(s) de outras plataformas puladas "
            "(use --no-easy-only para listá-las como candidatura manual).[/dim]"
        )

    # LinkedIn Easy Apply assistido
    if linkedin_jobs:
        try:
            with LinkedInClient(settings) as client:
                for job, match in linkedin_jobs:
                    console.print(f"\n[bold]>>> {job.title}[/bold] @ {job.company} (score {match.score:.0f})")
                    letter = generate_cover_letter(profile, job, settings)

                    if args.show_letter:
                        console.print(Panel(letter, title="Carta de apresentação"))

                    def on_step(msg: str) -> None:
                        console.print(f"  [dim]{msg}[/dim]")

                    ok = client.prepare_easy_apply(job, cover_letter=letter, on_step=on_step)
                    status = "prepared" if ok else "skipped"
                    storage.record_application(job, status=status)
                    if ok:
                        applied += 1
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrompido pelo usuário.[/yellow]")
        except Exception as exc:
            console.print(f"[red]Erro:[/red] {exc}")
            return 1

    console.print(f"\n[green]{applied} candidatura(s) processada(s).[/green]")
    return 0


def _load_ranked_jobs(storage: Storage, limit: int):
    ranked = storage.load_latest_rankings()
    if ranked:
        return [j for j, _ in ranked][:limit]
    return storage.load_jobs()[:limit]


def cmd_ats(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = Storage(settings.data_dir)

    profile = _load_profile(storage, settings)
    if not profile:
        return 1

    limit = args.limit or 5
    jobs = _load_ranked_jobs(storage, limit)
    if not jobs:
        console.print("[red]Nenhuma vaga salva.[/red] Execute: python -m cv_apply search")
        return 1

    resume_path = settings.resume_path if settings.resume_path.exists() else None
    reports = [analyze_ats(profile, job, resume_path) for job in jobs]

    # Relatório de formato (uma vez, do currículo)
    if reports and reports[0].format_checks:
        fmt = Table(title="Checagem de formato ATS do currículo")
        fmt.add_column("Item")
        fmt.add_column("Status")
        fmt.add_column("Detalhe")
        for check in reports[0].format_checks:
            status = "[green]OK[/green]" if check.passed else "[red]Falhou[/red]"
            fmt.add_row(check.name, status, check.detail)
        console.print(fmt)
        console.print(f"[bold]Score de formato:[/bold] {reports[0].format_score:.0f}/100\n")

    # ATS por vaga
    table = Table(title=f"ATS por vaga (top {len(reports)})")
    table.add_column("#", style="dim")
    table.add_column("ATS", style="bold green")
    table.add_column("Cobertura")
    table.add_column("Vaga")
    table.add_column("Faltando (palavras-chave)")
    for i, report in enumerate(reports, 1):
        missing = ", ".join(report.missing_keywords[:5]) or "-"
        table.add_row(
            str(i),
            f"{report.ats_score:.0f}",
            f"{report.keyword_coverage:.0f}%",
            report.job.title[:35],
            missing[:45],
        )
    console.print(table)

    # Agregado: o que mais falta no geral
    agg = aggregate_missing_keywords(reports, top=12)
    if agg:
        console.print("\n[bold]Palavras-chave que mais faltam (considere incluir se você tiver):[/bold]")
        console.print(", ".join(f"{kw} ({n})" for kw, n in agg))

    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    settings = get_settings()
    storage = Storage(settings.data_dir)

    profile = _load_profile(storage, settings)
    if not profile:
        return 1

    limit = args.limit or 3
    jobs = _load_ranked_jobs(storage, limit)
    if not jobs:
        console.print("[red]Nenhuma vaga salva.[/red] Execute: python -m cv_apply search e rank")
        return 1

    out_dir = settings.data_dir / "tailored"
    resume_path = settings.resume_path if settings.resume_path.exists() else None

    console.print(Panel(
        "Gerando currículo adaptado + carta para cada vaga.\n"
        "[yellow]São rascunhos[/yellow] baseados em palavras-chave — revise antes de enviar.",
        title="Tailor",
    ))

    for job in jobs:
        resume_md = save_tailored_resume(profile, job, out_dir, resume_path)
        letter = generate_cover_letter(profile, job, settings)
        letter_path = out_dir / (resume_md.stem + "_carta.txt")
        letter_path.write_text(letter, encoding="utf-8")
        console.print(f"[green]OK[/green] {job.title[:40]} @ {job.company[:25]}")
        console.print(f"   Currículo: {resume_md}")
        console.print(f"   Carta:     {letter_path}")

    console.print(f"\n[green]Arquivos gerados em[/green] {out_dir}")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    from cv_apply.webapp import run_server

    url = f"http://{args.host}:{args.port}"
    console.print(Panel(
        f"Interface web em [cyan]{url}[/cyan]\n"
        "Use Ctrl+C no terminal para parar.",
        title="Web",
    ))
    try:
        run_server(host=args.host, port=args.port, open_browser=not args.no_open)
    except KeyboardInterrupt:
        console.print("\n[yellow]Servidor encerrado.[/yellow]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv_apply",
        description="Auto Apply LinkedIn — modo assistido",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="Extrair perfil do currículo")
    p_parse.add_argument("resume", nargs="?", help="Caminho do PDF/DOCX")
    p_parse.set_defaults(func=cmd_parse)

    p_search = sub.add_parser("search", help="Buscar vagas (LinkedIn, Gupy, InfoJobs, APIs)")
    p_search.add_argument("--limit", type=int, help="Máximo de vagas por fonte")
    p_search.add_argument(
        "--sources",
        help="Fontes separadas por vírgula (linkedin,gupy,infojobs,remotive,remoteok)",
    )
    p_search.set_defaults(func=cmd_search)

    p_rank = sub.add_parser("rank", help="Ranquear vagas por compatibilidade")
    p_rank.add_argument("--min-score", type=float, help="Score mínimo (0-100)")
    p_rank.add_argument("--limit", type=int, help="Top N vagas")
    p_rank.add_argument("--csv", action="store_true", help="Exportar também em CSV")
    p_rank.set_defaults(func=cmd_rank)

    p_apply = sub.add_parser("apply", help="Preparar candidaturas (modo assistido)")
    p_apply.add_argument("--min-score", type=float, help="Score mínimo")
    p_apply.add_argument("--limit", type=int, help="Máximo de vagas nesta sessão")
    p_apply.add_argument(
        "--no-easy-only",
        dest="easy_only",
        action="store_false",
        default=True,
        help="Incluir vagas de outras plataformas como candidatura manual",
    )
    p_apply.add_argument(
        "--open-browser",
        action="store_true",
        help="Abrir links das candidaturas manuais no navegador",
    )
    p_apply.add_argument("--show-letter", action="store_true", help="Mostrar carta antes de aplicar")
    p_apply.set_defaults(func=cmd_apply)

    p_ats = sub.add_parser("ats", help="Analisar currículo vs vagas (ATS + palavras-chave)")
    p_ats.add_argument("--limit", type=int, help="Quantas vagas analisar (padrão 5)")
    p_ats.set_defaults(func=cmd_ats)

    p_tailor = sub.add_parser("tailor", help="Gerar currículo adaptado + carta por vaga")
    p_tailor.add_argument("--limit", type=int, help="Quantas vagas (padrão 3)")
    p_tailor.set_defaults(func=cmd_tailor)

    p_web = sub.add_parser("web", help="Abrir a interface web de busca de vagas")
    p_web.add_argument("--port", type=int, default=5000, help="Porta (padrão 5000)")
    p_web.add_argument("--host", default="127.0.0.1", help="Host (padrão 127.0.0.1)")
    p_web.add_argument("--no-open", action="store_true", help="Não abrir o navegador automaticamente")
    p_web.set_defaults(func=cmd_web)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))
