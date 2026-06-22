"""PIN opcional para proteger a interface web (uso em rede local/LAN)."""

from __future__ import annotations

import os

from flask import jsonify, request, session


def web_pin_enabled() -> bool:
    return bool((os.getenv("WEB_ACCESS_PIN") or "").strip())


def web_pin_ok() -> bool:
    if not web_pin_enabled():
        return True
    return session.get("web_pin_ok") is True


def register_web_auth(app) -> None:
    pin = (os.getenv("WEB_ACCESS_PIN") or "").strip()

    @app.before_request
    def _require_pin():
        if not pin:
            return None
        if request.path.startswith("/static/"):
            return None
        if request.endpoint in {"api_web_auth", "api_meta"}:
            return None
        if session.get("web_pin_ok"):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "PIN necessário.", "auth_required": True}), 401
        return None

    @app.route("/api/auth/pin", methods=["POST"])
    def api_web_auth():
        data = request.get_json(silent=True) or {}
        attempt = (data.get("pin") or "").strip()
        if attempt == pin:
            session["web_pin_ok"] = True
            return jsonify({"ok": True})
        return jsonify({"error": "PIN incorreto."}), 403
