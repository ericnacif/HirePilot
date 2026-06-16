"""Scheduler de alertas de vagas (web e desktop)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_started = False


def start_alert_scheduler(
    data_dir: Path,
    *,
    interval_minutes: int = 30,
    on_hits: Callable[[list], None] | None = None,
) -> None:
    """Inicia verificação periódica de alertas (idempotente)."""
    global _started
    if _started:
        return
    _started = True

    def _loop() -> None:
        while True:
            time.sleep(max(interval_minutes, 5) * 60)
            try:
                from cv_apply.alerts import run_all_enabled_alerts

                hits = run_all_enabled_alerts(data_dir)
                if hits and on_hits:
                    on_hits(hits)
            except Exception as exc:
                logger.debug("Scheduler de alertas: %s", exc)

    threading.Thread(target=_loop, name="hirepilot-alerts", daemon=True).start()
    logger.info("Alertas agendados a cada %d min.", interval_minutes)
