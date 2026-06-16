"""Alertas agendados de busca de vagas."""

from __future__ import annotations

import logging
from pathlib import Path

from cv_apply.config import Settings, get_settings
from cv_apply.profile import CandidateProfile
from cv_apply.search_pipeline import SearchContext, apply_payload_to_settings, execute_search
from cv_apply.storage import Storage

logger = logging.getLogger(__name__)


def _resolve_profile(storage: Storage, sid: str) -> CandidateProfile | None:
    profile = storage.load_web_profile(sid)
    if profile is not None:
        return profile
    return storage.load_profile()


def run_alert_check(
    storage: Storage,
    sid: str,
    alert: dict,
    profile: CandidateProfile | None = None,
) -> int:
    """Executa um alerta e retorna quantidade de vagas novas encontradas."""
    settings = get_settings()
    filters = alert.get("filters") or {}
    ctx = apply_payload_to_settings(filters, settings)
    ctx.only_new = True
    ctx.seen_job_ids = storage.get_seen_ids(sid)
    ctx.global_cap = 30

    if profile is None:
        profile = _resolve_profile(storage, sid)
    if profile is None:
        logger.warning("Alerta %s sem perfil — ignorado", alert.get("id"))
        return 0

    applied = set(storage.get_web_state(sid)["applied"].keys())
    result = execute_search(
        profile,
        settings,
        ctx,
        applied_ids=applied,
        format_posted=lambda v: v,
        use_cache=True,
    )
    new_count = len(result.jobs)
    if new_count:
        storage.mark_seen_jobs(sid, result.all_seen_ids)
    storage.update_alert_run(sid, alert["id"], new_count)
    return new_count


def run_all_enabled_alerts(data_dir: Path) -> list[dict]:
    """Roda todos os alertas habilitados; devolve resumo para notificação."""
    storage = Storage(data_dir)
    summaries: list[dict] = []
    for sid, alert in storage.enabled_alerts():
        try:
            n = run_alert_check(storage, sid, alert)
            if n:
                summaries.append({"sid": sid, "name": alert["name"], "new_count": n})
        except Exception as exc:
            logger.warning("Alerta %s falhou: %s", alert.get("id"), exc)
    return summaries
