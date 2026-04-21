"""
SQLite persistence for LAPA users, journal entries, weekly analytics, and baselines.
"""

from __future__ import annotations

import json
import logging
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)


class LapaStore:
    """
    Lightweight SQLite backend with optional session-based authentication.
    """

    def __init__(self, database_path: Path) -> None:
        """
        Args:
            database_path: Absolute or project-relative path to the SQLite file.
        """
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_schema(self) -> None:
        """Create tables and indexes if they are missing."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_public_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS journal_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_public_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    date TEXT NOT NULL,
                    week_id TEXT NOT NULL,
                    cleaned TEXT,
                    token_len INTEGER,
                    meta_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS weekly_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_public_id TEXT NOT NULL,
                    week_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS baselines (
                    user_public_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_journal_user ON journal_entries(user_public_id);
                CREATE INDEX IF NOT EXISTS idx_weekly_user ON weekly_results(user_public_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at);
                """
            )
        logger.info("SQLite schema ready at %s", self._path)

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def register_user(self, email: str, password: str, display_name: str) -> str:
        """
        Create a user row and return the public identifier used by the API.

        Raises:
            ValueError: If the email is already registered.
        """
        email_norm = email.strip().lower()
        if not email_norm or not password:
            raise ValueError("Email and password are required.")
        public_id = "u_" + secrets.token_hex(6)
        pw_hash = generate_password_hash(password)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (public_id, email, password_hash, display_name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (public_id, email_norm, pw_hash, display_name.strip() or email_norm, self._now_iso()),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Email already registered.") from exc
        logger.info("Registered user %s", public_id)
        return public_id

    def verify_user(self, email: str, password: str) -> Optional[str]:
        """Return ``public_id`` when credentials match."""
        email_norm = email.strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT public_id, password_hash FROM users WHERE email = ?",
                (email_norm,),
            ).fetchone()
        if not row:
            return None
        if not check_password_hash(str(row["password_hash"]), password):
            return None
        return str(row["public_id"])

    def create_session(self, public_id: str, ttl_hours: int = 720) -> str:
        """Issue a bearer token for the given user."""
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        expires = (now + timedelta(hours=ttl_hours)).replace(microsecond=0).isoformat() + "Z"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (token, user_public_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, public_id, self._now_iso(), expires),
            )
        return token

    def revoke_session(self, token: str) -> None:
        """Remove a session token."""
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def user_for_token(self, token: Optional[str]) -> Optional[str]:
        """Resolve a bearer token to ``public_id`` if still valid."""
        if not token:
            return None
        now = self._now_iso()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT user_public_id FROM sessions
                WHERE token = ? AND expires_at > ?
                """,
                (token, now),
            ).fetchone()
        return str(row["user_public_id"]) if row else None

    def prune_sessions(self) -> None:
        """Delete expired sessions (best-effort maintenance)."""
        now = self._now_iso()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

    def add_journal_entry(self, user_public_id: str, entry: Dict[str, Any]) -> None:
        """Persist a single journal row."""
        meta = entry.get("meta") or {}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO journal_entries
                (user_public_id, text, date, week_id, cleaned, token_len, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_public_id,
                    str(entry.get("text", "")),
                    str(entry.get("date", "")),
                    str(entry.get("week_id", "")),
                    str(entry.get("cleaned", "")),
                    int(entry.get("token_len", 0)),
                    json.dumps(meta),
                    self._now_iso(),
                ),
            )

    def list_journal_entries(self, user_public_id: str) -> List[Dict[str, Any]]:
        """Return all journal rows for analytics, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT text, date, week_id, cleaned, token_len, meta_json
                FROM journal_entries
                WHERE user_public_id = ?
                ORDER BY id ASC
                """,
                (user_public_id,),
            ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            meta = {}
            if row["meta_json"]:
                try:
                    meta = json.loads(str(row["meta_json"]))
                except json.JSONDecodeError:
                    meta = {}
            out.append(
                {
                    "text": row["text"],
                    "date": row["date"],
                    "week_id": row["week_id"],
                    "cleaned": row["cleaned"],
                    "token_len": int(row["token_len"] or 0),
                    "meta": meta,
                }
            )
        return out

    def append_weekly_result(self, user_public_id: str, payload: Dict[str, Any]) -> None:
        """Append a weekly analytic payload (mirrors JSONL semantics)."""
        week_id = str(payload.get("week_id", ""))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO weekly_results (user_public_id, week_id, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_public_id, week_id, json.dumps(payload), self._now_iso()),
            )

    def load_baseline_blob(self, user_public_id: str) -> Optional[str]:
        """Return raw JSON text for the user's baseline blob."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM baselines WHERE user_public_id = ?",
                (user_public_id,),
            ).fetchone()
        return str(row["payload_json"]) if row else None

    def save_baseline_blob(self, user_public_id: str, payload: Dict[str, Any]) -> None:
        """Upsert baseline JSON."""
        blob = json.dumps(payload)
        now = self._now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO baselines (user_public_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_public_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (user_public_id, blob, now),
            )

    def get_latest_weekly_payload(self, user_public_id: str) -> Dict[str, Any]:
        """Return the most recently stored weekly payload."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM weekly_results
                WHERE user_public_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_public_id,),
            ).fetchone()
        if not row:
            return {}
        try:
            return json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            return {}

    def build_indicator_dataframe(self, user_public_id: str) -> pd.DataFrame:
        """
        Build the longitudinal indicator frame, keeping the last row per ``week_id``.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT week_id, payload_json, id
                FROM weekly_results
                WHERE user_public_id = ?
                ORDER BY id ASC
                """,
                (user_public_id,),
            ).fetchall()
        last_by_week: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            try:
                obj = json.loads(str(row["payload_json"]))
            except json.JSONDecodeError:
                continue
            wid = str(row["week_id"])
            ind = obj.get("indicators", {})
            last_by_week[wid] = {
                "week_id": wid,
                "avoidance_score": ind.get("avoidance_score"),
                "topic_suppression_index": ind.get("topic_suppression_index"),
                "emotional_variability_score": ind.get("emotional_variability_score"),
                "flagged": ind.get("flagged"),
            }
        if not last_by_week:
            return pd.DataFrame(columns=["week_id", "avoidance_score", "topic_suppression_index", "emotional_variability_score"])
        df = pd.DataFrame(list(last_by_week.values()))
        return df.set_index("week_id")
