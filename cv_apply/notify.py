"""Notificações de alertas: desktop, Telegram e webhook genérico."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys

import httpx

logger = logging.getLogger(__name__)


def _desktop_enabled() -> bool:
    return os.getenv("NOTIFY_DESKTOP", "true").lower() in {"1", "true", "yes"}


def notify_desktop(title: str, message: str) -> bool:
    if not _desktop_enabled():
        return False
    title = (title or "HirePilot")[:120]
    message = (message or "")[:500]
    try:
        if sys.platform.startswith("win"):
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                "ContentType = WindowsRuntime] | Out-Null; "
                "$t = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('HirePilot'); "
                "$x = [Windows.UI.Notifications.ToastXml]::Create($t.GetTemplate("
                "[Windows.UI.Notifications.ToastTemplateType]::ToastText02)); "
                f"$x.GetElementsByTagName('text')[0].AppendChild($x.CreateTextNode('{title}')) | Out-Null; "
                f"$x.GetElementsByTagName('text')[1].AppendChild($x.CreateTextNode('{message}')) | Out-Null; "
                "$t.Show([Windows.UI.Notifications.ToastNotification]::new($x))"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True,
                timeout=8,
                check=False,
            )
            return True
        if sys.platform == "darwin":
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
            return True
    except Exception as exc:
        logger.debug("Notificação desktop falhou: %s", exc)
    return False


def notify_telegram(title: str, message: str) -> bool:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat_id:
        return False
    text = f"*{title}*\n{message}"
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("Telegram falhou: %s", exc)
        return False


def notify_webhook(title: str, message: str, *, extra: dict | None = None) -> bool:
    url = (os.getenv("NOTIFY_WEBHOOK_URL") or "").strip()
    if not url:
        return False
    payload = {"title": title, "message": message, **(extra or {})}
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json=payload)
            return resp.status_code < 400
    except Exception as exc:
        logger.warning("Webhook falhou: %s", exc)
        return False


def notify_alert_hits(hits: list[dict]) -> None:
    """Dispara todos os canais configurados para alertas com vagas novas."""
    if not hits:
        return
    for hit in hits:
        name = hit.get("name") or "Alerta"
        count = hit.get("new_count") or 0
        title = f"HirePilot — {name}"
        message = f"{count} vaga(s) nova(s) encontrada(s)."
        notify_desktop(title, message)
        notify_telegram(title, message)
        notify_webhook(title, message, extra={"alert": hit})
    logger.info("Notificações enviadas para %d alerta(s).", len(hits))
