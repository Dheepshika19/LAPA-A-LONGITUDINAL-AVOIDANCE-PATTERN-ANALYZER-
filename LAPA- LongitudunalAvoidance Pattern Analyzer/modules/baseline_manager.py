"""
Per-user longitudinal baselines with exponential moving averages.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from modules.lapa_store import LapaStore

logger = logging.getLogger(__name__)


class BaselineManager:
    """
    Tracks the first ``baseline_weeks`` of stable behavior and then EMA-updates.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        user_id: str,
        store: Optional["LapaStore"] = None,
    ) -> None:
        """
        Load an existing baseline snapshot or initialize empty structures.

        Args:
            config: Global configuration dictionary.
            user_id: Stable identifier for the journal author.
            store: Optional SQLite store; when provided, JSON files are not used.
        """
        self._config = config
        self.user_id = user_id
        self.baseline_weeks = int(config.get("baseline_weeks", 4))
        self.ema_decay = float(config.get("ema_decay", 0.9))
        self._store = store
        self._root = Path(config["data_paths"]["root"])
        rel = Path(config["data_paths"]["baselines_dir"])
        self._base_dir = rel if rel.is_absolute() else self._root / rel
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._base_dir / f"{user_id}.json"
        self._buffer: List[Dict[str, Any]] = []
        self.emotion_baseline: Dict[str, float] = {}
        self.topic_baseline: Dict[str, float] = {}
        self.vocab_richness: float = 0.0
        self.linguistic_variability: float = 0.0
        self.weeks_recorded: int = 0
        self.load_baseline(user_id)

    def _apply_payload(self, data: Dict[str, Any]) -> None:
        """Hydrate in-memory fields from a serialized baseline dictionary."""
        self.emotion_baseline = {k: float(v) for k, v in data.get("emotion_baseline", {}).items()}
        self.topic_baseline = {k: float(v) for k, v in data.get("topic_baseline", {}).items()}
        self.vocab_richness = float(data.get("vocab_richness", 0.0))
        self.linguistic_variability = float(data.get("linguistic_variability", 0.0))
        self.weeks_recorded = int(data.get("weeks_recorded", 0))
        self._buffer = list(data.get("buffer", []))

    def update_baseline(
        self,
        week_emotion: Dict[str, float],
        week_topics: Dict[str, float],
        week_id: str,
    ) -> None:
        """
        Accumulate weekly aggregates during the baseline establishment window.

        Args:
            week_emotion: Mean emotion probabilities for the week.
            week_topics: Normalized topic domain frequencies for the week.
            week_id: ISO week identifier used to de-duplicate rapid re-submissions.
        """
        if self.is_baseline_ready():
            return
        cats = list(self._config.get("emotion_categories", []))
        doms = list(self._config.get("topic_domains", []))
        emo = {c: float(week_emotion.get(c, 0.0)) for c in cats}
        top = {d: float(week_topics.get(d, 0.0)) for d in doms}
        vocab = float(week_emotion.get("_vocab_richness", 0.0))
        ling = float(week_emotion.get("_linguistic_variability", 0.0))
        record = {
            "week_id": week_id,
            "emotion": emo,
            "topics": top,
            "vocab": vocab,
            "ling": ling,
        }
        replaced = False
        for idx, row in enumerate(self._buffer):
            if row.get("week_id") == week_id:
                self._buffer[idx] = record
                replaced = True
                break
        if not replaced:
            self._buffer.append(record)
        self.weeks_recorded = len(self._buffer)
        if self.weeks_recorded >= self.baseline_weeks:
            self._finalize_baseline_from_buffer()
        logger.info(
            "Baseline buffer for user %s: %s/%s weeks (replaced=%s)",
            self.user_id,
            self.weeks_recorded,
            self.baseline_weeks,
            replaced,
        )

    def _finalize_baseline_from_buffer(self) -> None:
        cats = list(self._config.get("emotion_categories", []))
        doms = list(self._config.get("topic_domains", []))
        slice_rows = self._buffer[: self.baseline_weeks]
        self.emotion_baseline = {
            c: float(sum(r["emotion"][c] for r in slice_rows) / max(len(slice_rows), 1)) for c in cats
        }
        self.topic_baseline = {
            d: float(sum(r["topics"][d] for r in slice_rows) / max(len(slice_rows), 1)) for d in doms
        }
        self.vocab_richness = float(sum(r["vocab"] for r in slice_rows) / max(len(slice_rows), 1))
        self.linguistic_variability = float(sum(r["ling"] for r in slice_rows) / max(len(slice_rows), 1))

    def is_baseline_ready(self) -> bool:
        """Return True when enough longitudinal weeks exist."""
        return self.weeks_recorded >= self.baseline_weeks and bool(self.emotion_baseline)

    def update_ema(self, new_emotion: Dict[str, float], new_topics: Dict[str, float]) -> None:
        """
        Smoothly adapt baselines after the establishment phase.

        Args:
            new_emotion: Latest week emotion averages.
            new_topics: Latest week topic frequencies.
        """
        decay = self.ema_decay
        cats = list(self._config.get("emotion_categories", []))
        doms = list(self._config.get("topic_domains", []))
        if not self.emotion_baseline:
            self.emotion_baseline = {c: float(new_emotion.get(c, 0.0)) for c in cats}
        else:
            for c in cats:
                prev = float(self.emotion_baseline.get(c, 0.0))
                nxt = float(new_emotion.get(c, 0.0))
                self.emotion_baseline[c] = decay * prev + (1.0 - decay) * nxt
        if not self.topic_baseline:
            self.topic_baseline = {d: float(new_topics.get(d, 0.0)) for d in doms}
        else:
            for d in doms:
                prev = float(self.topic_baseline.get(d, 0.0))
                nxt = float(new_topics.get(d, 0.0))
                self.topic_baseline[d] = decay * prev + (1.0 - decay) * nxt
        vr = float(new_emotion.get("_vocab_richness", 0.0))
        lv = float(new_emotion.get("_linguistic_variability", 0.0))
        self.vocab_richness = decay * self.vocab_richness + (1.0 - decay) * vr
        self.linguistic_variability = decay * self.linguistic_variability + (1.0 - decay) * lv

    def save_baseline(self) -> None:
        """Persist baseline statistics for the active user."""
        payload = {
            "user_id": self.user_id,
            "emotion_baseline": self.emotion_baseline,
            "topic_baseline": self.topic_baseline,
            "vocab_richness": self.vocab_richness,
            "linguistic_variability": self.linguistic_variability,
            "weeks_recorded": self.weeks_recorded,
            "buffer": self._buffer,
        }
        if self._store:
            self._store.save_baseline_blob(self.user_id, payload)
            logger.info("Saved baseline for %s to SQLite", self.user_id)
        else:
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.info("Saved baseline for %s to %s", self.user_id, self._path)

    def load_baseline(self, user_id: str) -> None:
        """
        Load baseline data for a user from SQLite or JSON on disk.

        Args:
            user_id: Identifier matching the persisted record.
        """
        self.user_id = user_id
        if self._store:
            raw = self._store.load_baseline_blob(user_id)
            if raw:
                self._apply_payload(json.loads(raw))
            else:
                self._buffer = []
                self.emotion_baseline = {}
                self.topic_baseline = {}
                self.vocab_richness = 0.0
                self.linguistic_variability = 0.0
                self.weeks_recorded = 0
                logger.info("No SQLite baseline for %s — starting fresh.", user_id)
            return
        path = self._base_dir / f"{user_id}.json"
        if not path.exists():
            logger.warning("No baseline file for %s", user_id)
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self._apply_payload(data)
