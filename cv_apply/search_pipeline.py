"""Pipeline compartilhado de busca: fontes → filtros → ranking → API."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from cv_apply.ats import analyze_ats
from cv_apply.config import Settings
from cv_apply.locations import LocationFilter, parse_location
from cv_apply.matching import apply_keyword_boost, apply_preference_boost, rank_jobs
from cv_apply.profile import CandidateProfile, JobMatch, JobPosting
from cv_apply.relevance import (
    extract_query_terms,
    filter_by_experience,
    filter_by_location,
    filter_by_relevance,
)
from cv_apply.salary import extract_salary, filter_by_salary
from cv_apply.sectors import (
    apply_sector_boost,
    sector_gate_terms,
    sector_query,
    sector_search_queries,
)
from cv_apply.sources import AVAILABLE_SOURCES, dedupe_jobs, run_sources

GLOBAL_JOB_CAP = 100


def posted_sort_key(value: str | None) -> float:
    """Timestamp para ordenar vagas por data (mais recente = maior)."""
    if not value:
        return 0.0
    raw = value.strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return 0.0


@dataclass
class SearchContext:
    user_keywords: str = ""
    sector: str = ""
    broad: bool = True
    salary_min: float | None = None
    salary_max: float | None = None
    only_new: bool = False
    use_semantic: bool = True
    limit_per_source: int = 40
    global_cap: int = GLOBAL_JOB_CAP
    seen_job_ids: set[str] = field(default_factory=set)
    location_filter: LocationFilter | None = None


def apply_payload_to_settings(data: dict, settings: Settings) -> SearchContext:
    """Aplica JSON do front-end às configurações e devolve o contexto."""
    user_keywords = (data.get("keywords") or "").strip()
    sector = data.get("sector", "")
    broad = data.get("broad", True)
    settings.broad_mode = bool(broad)

    if user_keywords:
        settings.search_keywords = user_keywords
        parts = [p.strip() for p in re.split(r"[,;/]+", user_keywords) if p.strip()]
        settings.search_queries = parts if len(parts) > 1 else [user_keywords]
    elif sector:
        settings.search_queries = sector_search_queries(sector)
        settings.search_keywords = sector_query(sector) or (
            settings.search_queries[0] if settings.search_queries else "tecnologia"
        )
    else:
        settings.search_keywords = "tecnologia"
        settings.search_queries = sector_search_queries("tec_all")

    loc_filter = parse_location(
        data.get("location") or "",
        scope=data.get("location_scope"),
        city=data.get("location_city"),
        state=data.get("location_state"),
        include_remote=bool(data.get("location_include_remote")),
    )
    settings.search_location = loc_filter.indeed_query() or loc_filter.display_label()

    settings.search_workplace = [w.lower() for w in data.get("workplace", [])]
    settings.search_job_type = [j.lower() for j in data.get("job_type", [])]
    settings.search_experience = [e.lower() for e in data.get("experience", [])]
    settings.search_date_posted = (data.get("date_posted") or "qualquer").lower()

    sources = [s.lower() for s in data.get("sources", []) if s.lower() in AVAILABLE_SOURCES]
    settings.search_sources = sources or ["gupy"]

    use_semantic = data.get("semantic")
    if use_semantic is not None:
        settings.use_semantic_matching = bool(use_semantic)
    elif "semantic" in data:
        settings.use_semantic_matching = bool(data["semantic"])

    limit = max(1, min(int(data.get("limit") or 40), 100))
    n_sources = max(len(sources), 1)
    default_cap = limit * n_sources
    global_cap_raw = data.get("global_cap")
    if broad:
        # Modo amplo: por padrão não corta o ranking global — até ``limit`` por fonte.
        if global_cap_raw in (None, "", 0):
            global_cap = 0
        else:
            global_cap = max(10, min(int(global_cap_raw), 1000))
    else:
        global_cap = max(10, min(int(global_cap_raw or default_cap), 1000))

    sal_min = data.get("salary_min")
    sal_max = data.get("salary_max")
    ctx = SearchContext(
        user_keywords=user_keywords,
        sector=sector,
        broad=bool(broad),
        salary_min=float(sal_min) if sal_min not in (None, "", 0) else None,
        salary_max=float(sal_max) if sal_max not in (None, "", 0) else None,
        only_new=bool(data.get("only_new")),
        use_semantic=settings.use_semantic_matching,
        limit_per_source=limit,
        global_cap=global_cap,
        seen_job_ids=set(data.get("seen_ids") or []),
        location_filter=loc_filter,
    )
    return ctx


def _count_by_source(jobs: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for j in jobs:
        src = j.get("source") or "—"
        counts[src] = counts.get(src, 0) + 1
    return counts


def process_raw_jobs(
    all_jobs: list[JobPosting],
    ctx: SearchContext,
    settings: Settings,
) -> list[JobPosting]:
    """Dedupe, localização, senioridade, relevância e salário."""
    if not all_jobs:
        return []

    all_jobs = dedupe_jobs(all_jobs)

    filt = ctx.location_filter or parse_location(settings.search_location)
    if filt.scope.value != "any":
        use_fallback = not filt.strict and (not filt.is_specific and ctx.broad)
        all_jobs = filter_by_location(
            all_jobs,
            settings.search_location,
            fallback=use_fallback,
            location_filter=filt,
        )

    # Modo amplo: filtros refinados viram preferência no ranking, não exclusão.
    if not ctx.broad:
        all_jobs = filter_by_salary(all_jobs, ctx.salary_min, ctx.salary_max)
        all_jobs = filter_by_experience(all_jobs, settings.search_experience)
        user_terms = extract_query_terms(ctx.user_keywords)
        gate_terms = user_terms or sector_gate_terms(ctx.sector)
        all_jobs = filter_by_relevance(all_jobs, gate_terms, fallback=False)
    else:
        if ctx.salary_min is not None or ctx.salary_max is not None:
            all_jobs = filter_by_salary(all_jobs, ctx.salary_min, ctx.salary_max)

    return all_jobs


def rank_and_boost(
    profile: CandidateProfile,
    jobs: list[JobPosting],
    ctx: SearchContext,
    settings: Settings,
    *,
    use_semantic: bool | None = None,
) -> list[JobMatch]:
    sem = ctx.use_semantic if use_semantic is None else use_semantic
    matches = rank_jobs(profile, jobs, min_score=0, use_semantic=sem)
    matches = apply_sector_boost(matches, ctx.sector)
    if ctx.user_keywords:
        matches = apply_keyword_boost(matches, ctx.user_keywords)
    if ctx.broad:
        matches = apply_preference_boost(matches, settings, location_filter=ctx.location_filter)
    return matches


def apply_display_limits(
    matches: list[JobMatch],
    source_by_id: dict[str, str],
    ctx: SearchContext,
) -> tuple[list[JobMatch], dict]:
    """Aplica teto de exibição. Em modo amplo: até ``limit_per_source`` por fonte."""
    meta: dict = {"truncated": False, "truncation": None}
    if not matches:
        return matches, meta

    before = len(matches)
    if ctx.broad:
        by_src: dict[str, list[JobMatch]] = defaultdict(list)
        for m in matches:
            by_src[source_by_id.get(m.job.id, "")].append(m)
        limited: list[JobMatch] = []
        for items in by_src.values():
            limited.extend(items[: ctx.limit_per_source])
        limited.sort(key=lambda m: m.score, reverse=True)
        if ctx.global_cap and len(limited) > ctx.global_cap:
            meta["truncated"] = True
            meta["truncation"] = "global_cap"
            return limited[: ctx.global_cap], meta
        if len(limited) < before:
            meta["truncated"] = True
            meta["truncation"] = "per_source"
        return limited, meta

    if ctx.global_cap and len(matches) > ctx.global_cap:
        meta["truncated"] = True
        meta["truncation"] = "global_cap"
        return matches[: ctx.global_cap], meta
    return matches, meta


def job_row(
    m: JobMatch,
    profile: CandidateProfile,
    *,
    source: str,
    applied: bool,
    is_new: bool,
    format_posted,
) -> dict:
    report = analyze_ats(profile, m.job, resume_path=None)
    desc = (m.job.description or "").strip().replace("\n", " ")
    if len(desc) > 220:
        desc = desc[:220].rsplit(" ", 1)[0] + "…"
    _, _, sal_text = extract_salary(m.job)
    return {
        "id": m.job.id,
        "title": m.job.title,
        "company": m.job.company,
        "location": m.job.location,
        "url": m.job.url,
        "score": m.score,
        "ats": report.keyword_coverage,
        "skills": m.skill_overlap[:8],
        "reasons": m.reasons,
        "reasons_short": "; ".join(m.reasons[:2]),
        "cv_tips": report.suggestions[:3],
        "source": source,
        "posted_at": format_posted(m.job.posted_at),
        "posted_sort": posted_sort_key(m.job.posted_at),
        "easy_apply": m.job.easy_apply,
        "description": desc,
        "salary": sal_text,
        "applied": applied,
        "is_new": is_new,
    }


@dataclass
class SearchResult:
    jobs: list[dict]
    sources_status: list[dict]
    meta: dict
    job_models: dict[str, JobPosting]
    source_by_id: dict[str, str]
    all_seen_ids: list[str]


def _sources_status(
    settings: Settings,
    results: dict[str, list[JobPosting]],
    shown_by_source: dict[str, int] | None = None,
    source_meta: dict[str, dict] | None = None,
) -> list[dict]:
    shown_by_source = shown_by_source or {}
    source_meta = source_meta or {}
    return [
        {
            "source": name,
            "fetched": len(results.get(name, [])),
            "shown": shown_by_source.get(name, 0),
            "count": shown_by_source.get(name, 0) or len(results.get(name, [])),
            "cached": bool(source_meta.get(name, {}).get("cached")),
            "hint": source_meta.get(name, {}).get("hint"),
        }
        for name in settings.search_sources
    ]


def _assemble_result(
    profile: CandidateProfile,
    settings: Settings,
    ctx: SearchContext,
    *,
    applied_ids: set[str],
    format_posted,
    all_jobs: list[JobPosting],
    source_by_id: dict[str, str],
    raw_by_source: dict[str, list[JobPosting]],
    t0: float,
    source_meta: dict[str, dict] | None = None,
    fast_rank: bool = False,
) -> SearchResult:
    source_meta = source_meta or {}
    sources_status = _sources_status(settings, raw_by_source, source_meta=source_meta)
    fetched_count = len(dedupe_jobs(all_jobs)) if all_jobs else 0
    filtered = process_raw_jobs(all_jobs, ctx, settings)

    if not filtered:
        filt = ctx.location_filter
        loc_hint = ""
        if filt and filt.is_specific and fetched_count:
            loc_hint = (
                f"Nenhuma vaga em {filt.display_label()} com os filtros atuais. "
                "Tente ampliar para o estado inteiro ou marcar «Incluir remotas»."
            )
        elif filt and filt.is_specific:
            loc_hint = (
                f"Buscamos em {filt.display_label()}. "
                "Poucas vagas listadas nessa região — tente outra área ou fontes."
            )
        return SearchResult(
            jobs=[],
            sources_status=sources_status,
            meta={
                "broad": ctx.broad,
                "fetched": fetched_count,
                "shown": 0,
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                "cached": False,
                "by_source": {},
                "by_source_fetched": {n: len(raw_by_source.get(n, [])) for n in settings.search_sources},
                "location_label": filt.display_label() if filt else "",
                "location_scope": filt.scope.value if filt else "",
                "location_hint": loc_hint,
            },
            job_models={},
            source_by_id=source_by_id,
            all_seen_ids=list(ctx.seen_job_ids),
        )

    matches, limit_meta = apply_display_limits(
        rank_and_boost(
            profile, filtered, ctx, settings,
            use_semantic=False if fast_rank else None,
        ),
        source_by_id,
        ctx,
    )
    out: list[dict] = []
    job_models: dict[str, JobPosting] = {}
    new_ids = set(ctx.seen_job_ids)
    shown_by_source: dict[str, int] = {}

    for m in matches:
        new_ids.add(m.job.id)
        if ctx.only_new and m.job.id in ctx.seen_job_ids:
            continue
        is_new = m.job.id not in ctx.seen_job_ids
        job_models[m.job.id] = m.job
        src = source_by_id.get(m.job.id, "")
        shown_by_source[src] = shown_by_source.get(src, 0) + 1
        out.append(
            job_row(
                m,
                profile,
                source=src,
                applied=m.job.id in applied_ids,
                is_new=is_new,
                format_posted=format_posted,
            )
        )

    sources_status = _sources_status(
        settings, raw_by_source, shown_by_source, source_meta=source_meta,
    )

    any_cached = any(source_meta.get(n, {}).get("cached") for n in settings.search_sources)

    return SearchResult(
        jobs=out,
        sources_status=sources_status,
        meta={
            "broad": ctx.broad,
            "fetched": fetched_count,
            "shown": len(out),
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "new_count": sum(1 for j in out if j.get("is_new")),
            "by_source": shown_by_source,
            "by_source_fetched": {n: len(raw_by_source.get(n, [])) for n in settings.search_sources},
            "limit_per_source": ctx.limit_per_source,
            "global_cap": ctx.global_cap,
            "truncated": limit_meta.get("truncated", False),
            "truncation": limit_meta.get("truncation"),
            "after_filters": len(filtered),
            "cached": any_cached,
            "fast_rank": fast_rank,
            "location_label": (ctx.location_filter.display_label() if ctx.location_filter else ""),
            "location_scope": (ctx.location_filter.scope.value if ctx.location_filter else ""),
        },
        job_models=job_models,
        source_by_id=source_by_id,
        all_seen_ids=list(new_ids),
    )


def execute_search(
    profile: CandidateProfile,
    settings: Settings,
    ctx: SearchContext,
    *,
    applied_ids: set[str],
    format_posted,
    on_source_done: Callable[[str, list[JobPosting]], None] | None = None,
    on_partial: Callable[[SearchResult], None] | None = None,
    use_cache: bool = True,
    t0: float | None = None,
) -> SearchResult:
    """Busca completa; ``on_partial`` re-ranqueia e notifica após cada fonte."""
    t0 = t0 or time.perf_counter()
    all_jobs: list[JobPosting] = []
    source_by_id: dict[str, str] = {}
    raw_by_source: dict[str, list[JobPosting]] = {}
    source_meta: dict[str, dict] = {}

    def _after_source(name: str, jobs: list[JobPosting]) -> None:
        raw_by_source[name] = jobs
        for job in jobs:
            source_by_id[job.id] = name
            all_jobs.append(job)
        if on_source_done:
            on_source_done(name, jobs)
        if on_partial:
            on_partial(
                _assemble_result(
                    profile,
                    settings,
                    ctx,
                    applied_ids=applied_ids,
                    format_posted=format_posted,
                    all_jobs=list(all_jobs),
                    source_by_id=dict(source_by_id),
                    raw_by_source=dict(raw_by_source),
                    t0=t0,
                    source_meta=dict(source_meta),
                    fast_rank=True,
                )
            )

    _, source_meta = run_sources(
        settings,
        max_jobs=ctx.limit_per_source,
        on_log=None,
        on_source_done=_after_source,
        use_cache=use_cache,
    )

    return _assemble_result(
        profile,
        settings,
        ctx,
        applied_ids=applied_ids,
        format_posted=format_posted,
        all_jobs=all_jobs,
        source_by_id=source_by_id,
        raw_by_source=raw_by_source,
        t0=t0,
        source_meta=source_meta,
        fast_rank=False,
    )
