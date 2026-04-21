"""
Flask dashboard and JSON API for LAPA.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS

from dashboard.chat_proxy import compose_chat_reply, local_fallback_reply
from pipeline.controller import PipelineController
from pipeline.reporter import Reporter

logger = logging.getLogger(__name__)


def _bearer_token() -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-LAPA-Token", "") or "").strip() or None


def create_app(config_path: str | None = None) -> Flask:
    """
    Application factory wiring routes to the analytic pipeline.

    Args:
        config_path: Optional override for ``config/config.yaml``.

    Returns:
        Configured Flask application.
    """
    base = Path(__file__).resolve().parents[1]
    cfg_path = Path(config_path) if config_path else base / "config" / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    cors_origins = cfg.get("dashboard", {}).get("cors_origins", "*")
    CORS(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        allow_headers=["Authorization", "Content-Type", "X-LAPA-Token"],
    )

    require_auth = bool(cfg.get("dashboard", {}).get("require_auth", False))

    controller = PipelineController(str(cfg_path))
    store = getattr(controller, "_store", None)
    if require_auth and store is None:
        logger.error(
            "dashboard.require_auth is enabled but storage.backend is not sqlite — forcing require_auth off."
        )
        require_auth = False
    reporter = Reporter(cfg)
    app.config["LAPA_CONTROLLER"] = controller
    app.config["LAPA_REPORTER"] = reporter
    app.config["LAPA_CONFIG"] = cfg
    app.config["LAPA_STORE"] = store
    app.config["LAPA_REQUIRE_AUTH"] = require_auth

    def resolve_actor_user() -> Tuple[Optional[str], Optional[Tuple[Any, int]]]:
        """Return ``(actor_user_id, (response, status))`` on failure."""
        token_user: Optional[str] = None
        if store:
            token_user = store.user_for_token(_bearer_token())
        payload = request.get_json(silent=True) or {}
        explicit = request.values.get("user_id") or payload.get("user_id")
        explicit_str = str(explicit) if explicit else None
        default_uid = str(cfg.get("dashboard", {}).get("default_user_id", "demo_user"))
        if require_auth:
            if not token_user:
                return None, (jsonify({"error": "unauthorized", "detail": "Bearer token required"}), 401)
            return token_user, None
        if token_user:
            return token_user, None
        return explicit_str or default_uid, None

    @app.route("/")
    def home() -> Any:
        """Serve the integrated mobile shell with API base injected."""
        rel = Path(cfg.get("dashboard", {}).get("frontend_path", "frontend/lapa_mobile_app.html"))
        html_path = rel if rel.is_absolute() else base / rel
        html = html_path.read_text(encoding="utf-8")
        api_root = "/api"
        injection = (
            "<script>"
            f"window.LAPA_API={json.dumps(api_root)};"
            f"window.LAPA_USER={json.dumps(cfg.get('dashboard', {}).get('default_user_id', 'demo_user'))};"
            f"window.LAPA_REQUIRE_AUTH={json.dumps(require_auth)};"
            "</script>"
        )
        return injection + html

    @app.route("/dashboard/<user_id>")
    def dashboard(user_id: str) -> str:
        """Bootstrap clinical dashboard."""
        history = controller.get_user_history(user_id)
        summary = reporter.generate_longitudinal_summary(user_id, history)
        return render_template(
            "index.html",
            user_id=user_id,
            history=history.reset_index().to_dict(orient="records"),
            summary=summary,
            threshold=float(cfg.get("avoidance_threshold", 0.65)),
            watch=float(cfg.get("watch_threshold_low", 0.4)),
        )

    @app.post("/api/v1/auth/register")
    def api_register() -> Any:
        """Create a local account and return a bearer token."""
        if not store:
            return jsonify({"error": "sqlite_required"}), 503
        payload = request.get_json(force=True, silent=True) or {}
        email = str(payload.get("email", "")).strip()
        password = str(payload.get("password", "")).strip()
        display_name = str(payload.get("display_name", "")).strip()
        try:
            public_id = store.register_user(email, password, display_name or email.split("@")[0])
            token = store.create_session(public_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"status": "ok", "user_id": public_id, "token": token})

    @app.post("/api/v1/auth/login")
    def api_login() -> Any:
        """Exchange email/password for a bearer token."""
        if not store:
            return jsonify({"error": "sqlite_required"}), 503
        payload = request.get_json(force=True, silent=True) or {}
        email = str(payload.get("email", "")).strip()
        password = str(payload.get("password", "")).strip()
        public_id = store.verify_user(email, password)
        if not public_id:
            return jsonify({"error": "invalid_credentials"}), 401
        token = store.create_session(public_id)
        return jsonify({"status": "ok", "user_id": public_id, "token": token})

    @app.post("/api/v1/auth/logout")
    def api_logout() -> Any:
        """Invalidate the active bearer token."""
        token = _bearer_token()
        if store and token:
            store.revoke_session(token)
        return jsonify({"status": "ok"})

    @app.post("/submit_entry")
    def submit_entry_legacy() -> Any:
        """Backward-compatible form endpoint."""
        actor, err = resolve_actor_user()
        if err:
            return err
        payload = request.get_json(force=True, silent=True) or request.form
        user_id = str(payload.get("user_id") or actor)
        if require_auth and user_id != actor:
            return jsonify({"error": "forbidden"}), 403
        text = str(payload.get("text", ""))
        date = str(payload.get("date", ""))
        result = controller.process_entry(user_id, text, date)
        return jsonify(result)

    @app.post("/api/v1/entries")
    def api_submit_entry() -> Any:
        """JSON API used by the mobile frontend."""
        actor, err = resolve_actor_user()
        if err:
            return err
        payload = request.get_json(force=True, silent=True) or {}
        user_id = str(payload.get("user_id") or actor)
        if require_auth and user_id != actor:
            return jsonify({"error": "forbidden"}), 403
        text = str(payload.get("text", ""))
        date = str(payload.get("date", ""))
        mood = payload.get("mood")
        topics = payload.get("topics", [])
        meta = {"mood": mood, "topics": topics}
        merged = controller.process_entry(user_id, text, date, meta=meta)
        return jsonify({"status": "ok", "pipeline": merged})

    @app.post("/api/v1/chat")
    def api_chat() -> Any:
        """Supportive chat with optional OpenAI-compatible backend."""
        actor, err = resolve_actor_user()
        if err:
            return err
        payload = request.get_json(force=True, silent=True) or {}
        user_id = str(payload.get("user_id") or actor)
        if require_auth and user_id != actor:
            return jsonify({"error": "forbidden"}), 403
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify({"error": "empty_message"}), 400
        remote = compose_chat_reply(message, cfg)
        if remote:
            return jsonify({"status": "ok", "reply": remote, "source": "remote"})
        return jsonify({"status": "ok", "reply": local_fallback_reply(), "source": "local"})

    @app.get("/api/v1/insights/<user_id>")
    def api_insights(user_id: str) -> Any:
        """Return the latest weekly analytic bundle."""
        actor, err = resolve_actor_user()
        if err:
            return err
        uid = user_id
        if require_auth and uid != actor:
            return jsonify({"error": "forbidden"}), 403
        target = actor if require_auth else (actor or uid)
        history = controller.get_user_history(target)
        if history.empty:
            return jsonify({"status": "empty", "indicators": None, "history": []})
        last_week = history.reset_index().iloc[-1].to_dict()
        indicators = {
            "avoidance_score": float(last_week.get("avoidance_score", 0.0)),
            "topic_suppression_index": float(last_week.get("topic_suppression_index", 0.0)),
            "emotional_variability_score": float(last_week.get("emotional_variability_score", 0.0)),
            "flagged": bool(last_week.get("flagged", False)),
        }
        detail = controller.get_latest_weekly_record(target)
        report = reporter.generate_weekly_report(
            target,
            str(last_week.get("week_id", "")),
            detail.get("indicators", indicators),
        )
        hist_records = history.reset_index().tail(8).to_dict(orient="records")
        return jsonify({"status": "ok", "indicators": indicators, "report": report, "history": hist_records})

    @app.get("/api/v1/history/<user_id>")
    def api_history(user_id: str) -> Any:
        """Return longitudinal indicator rows."""
        actor, err = resolve_actor_user()
        if err:
            return err
        if require_auth and user_id != actor:
            return jsonify({"error": "forbidden"}), 403
        target = actor if require_auth else (actor or user_id)
        history = controller.get_user_history(target)
        return jsonify({"status": "ok", "rows": history.reset_index().tail(16).to_dict(orient="records")})

    @app.get("/history/<user_id>")
    def history_page(user_id: str) -> str:
        """Simple longitudinal table view."""
        history = controller.get_user_history(user_id)
        return render_template("history.html", user_id=user_id, rows=history.reset_index().to_dict(orient="records"))

    @app.get("/report/<user_id>")
    def download_report(user_id: str) -> Any:
        """Download the latest structured JSON report."""
        history = controller.get_user_history(user_id)
        summary = reporter.generate_longitudinal_summary(user_id, history)
        payload = {"user_id": user_id, "summary": summary, "history": history.reset_index().to_dict(orient="records")}
        out = Path(__file__).parent / "static" / f"{user_id}_report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return send_file(out, as_attachment=True, download_name=f"{user_id}_lapa_report.json")

    return app


def run() -> None:
    """CLI helper to launch the development server."""
    logging.basicConfig(level=logging.INFO)
    base = Path(__file__).resolve().parents[1]
    cfg_path = base / "config" / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    host = cfg.get("dashboard", {}).get("host", "127.0.0.1")
    port = int(cfg.get("dashboard", {}).get("port", 5000))
    app = create_app(str(cfg_path))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
