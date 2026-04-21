"""
End-to-end orchestration for LAPA journal processing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from modules.baseline_manager import BaselineManager
from modules.deviation_analyzer import DeviationAnalyzer
from modules.emotion_classifier import EmotionClassifier
from modules.indicator_generator import IndicatorGenerator
from modules.lapa_store import LapaStore
from modules.preprocessor import TextPreprocessor
from modules.topic_modeler import TopicModeler

logger = logging.getLogger(__name__)


class PipelineController:
    """
    Coordinates preprocessing, modeling, baselines, and indicator generation.
    """

    def __init__(self, config_path: str) -> None:
        """
        Load YAML configuration and construct all analytic modules.

        Args:
            config_path: Path to ``config/config.yaml``.
        """
        self._config_path = Path(config_path)
        with self._config_path.open("r", encoding="utf-8") as handle:
            self.config: Dict[str, Any] = yaml.safe_load(handle)
        root = Path(self.config["data_paths"]["root"])
        for key in ("raw", "processed", "models", "baselines_dir", "user_entries_dir", "weekly_results_dir"):
            rel = Path(self.config["data_paths"][key])
            path = rel if rel.is_absolute() else root / rel
            path.mkdir(parents=True, exist_ok=True)
        storage = self.config.get("storage", {}) or {}
        backend = str(storage.get("backend", "sqlite")).lower()
        self._store: Optional[LapaStore] = None
        if backend == "sqlite":
            db_rel = Path(storage.get("database_path", "data/processed/lapa.sqlite"))
            db_path = db_rel if db_rel.is_absolute() else root / db_rel
            self._store = LapaStore(db_path)
            self._store.init_schema()
            self._store.prune_sessions()
            logger.info("Using SQLite storage at %s", db_path)
        elif backend != "json":
            logger.warning("Unknown storage.backend=%s — defaulting to JSON files.", backend)
        self.preprocessor = TextPreprocessor(self.config)
        model_dir = root / self.config["data_paths"]["emotion_model_dir"]
        self.emotion_classifier = EmotionClassifier(str(model_dir), self.config)
        self.topic_modeler = TopicModeler(self.config)
        self.indicator_generator = IndicatorGenerator(self.config)
        self._baseline_cache: Dict[str, BaselineManager] = {}
        logger.info("PipelineController initialized from %s", self._config_path)

    def _user_entries_path(self, user_id: str) -> Path:
        root = Path(self.config["data_paths"]["root"])
        rel = Path(self.config["data_paths"]["user_entries_dir"])
        base = rel if rel.is_absolute() else root / rel
        return base / f"{user_id}.json"

    def _weekly_results_path(self, user_id: str) -> Path:
        root = Path(self.config["data_paths"]["root"])
        rel = Path(self.config["data_paths"]["weekly_results_dir"])
        base = rel if rel.is_absolute() else root / rel
        return base / f"{user_id}_weekly.jsonl"

    def _load_entries(self, user_id: str) -> List[Dict[str, Any]]:
        if self._store:
            return self._store.list_journal_entries(user_id)
        path = self._user_entries_path(user_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_entries(self, user_id: str, entries: List[Dict[str, Any]]) -> None:
        path = self._user_entries_path(user_id)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _persist_entry(self, user_id: str, entry: Dict[str, Any]) -> None:
        if self._store:
            self._store.add_journal_entry(user_id, entry)
            return
        entries = self._load_entries(user_id)
        entries.append(entry)
        self._save_entries(user_id, entries)

    def _get_baseline_manager(self, user_id: str) -> BaselineManager:
        if user_id not in self._baseline_cache:
            self._baseline_cache[user_id] = BaselineManager(self.config, user_id, store=self._store)
        return self._baseline_cache[user_id]

    def get_latest_weekly_record(self, user_id: str) -> Dict[str, Any]:
        """
        Return the most recent weekly analytic payload for dashboards.

        Args:
            user_id: Subject identifier.

        Returns:
            Parsed weekly JSON dictionary (possibly empty).
        """
        if self._store:
            return dict(self._store.get_latest_weekly_payload(user_id))
        path = self._weekly_results_path(user_id)
        if not path.exists():
            return {}
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            return {}
        return json.loads(lines[-1])

    def process_entry(
        self,
        user_id: str,
        text: str,
        date: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingest a single journal entry and optionally refresh weekly analytics.

        Args:
            user_id: Stable user identifier.
            text: Raw journal text.
            date: ISO date ``YYYY-MM-DD``.
            meta: Optional client metadata (mood tags, selected topics, etc.).

        Returns:
            Status dictionary with cleaning metadata and optional indicators.
        """
        if not text or not str(text).strip():
            logger.warning("Empty journal text for user %s — skipping.", user_id)
            return {"status": "ignored", "reason": "empty_text"}
        cleaned = self.preprocessor.clean_text(text)
        tokens = self.preprocessor.tokenize(text)
        week_id = TextPreprocessor._week_key(date)
        row = {
            "text": text,
            "date": date,
            "week_id": week_id,
            "cleaned": cleaned,
            "token_len": int(tokens["input_ids"].shape[1]),
            "meta": meta or {},
        }
        self._persist_entry(user_id, row)
        logger.info("Stored entry for user %s week %s", user_id, week_id)
        out: Dict[str, Any] = {
            "status": "stored",
            "week_id": week_id,
            "cleaned_preview": cleaned[:280],
        }
        if bool(self.config.get("demo", {}).get("analyze_on_submit", True)):
            weekly = self.run_weekly_analysis(user_id, week_id)
            out["weekly_analysis"] = weekly
        return out

    def run_weekly_analysis(self, user_id: str, week_id: int | str) -> Dict[str, Any]:
        """
        Aggregate a week's worth of text and refresh longitudinal indicators.

        Args:
            user_id: User identifier.
            week_id: ISO week key string ``YYYY-Www`` (preferred) or ignored int for compatibility.

        Returns:
            Indicator dictionary or baseline status message.
        """
        entries = self._load_entries(user_id)
        if isinstance(week_id, int):
            windows = self.preprocessor.segment_to_weekly_windows(entries)
            keys = sorted(windows.keys())
            if week_id < 0 or week_id >= len(keys):
                return {"status": "error", "reason": "invalid_week_index"}
            target_week = keys[week_id]
        else:
            target_week = str(week_id)
        windows = self.preprocessor.segment_to_weekly_windows(entries)
        if target_week not in windows:
            return {"status": "no_data", "week_id": target_week}
        week_entries = windows[target_week]
        texts = [str(e.get("text", "")) for e in week_entries]
        emo_matrix = self.emotion_classifier.get_weekly_emotion_matrix({target_week: week_entries})
        topic_matrix = self.topic_modeler.get_weekly_topic_matrix({target_week: week_entries})
        emotion_row = emo_matrix.loc[target_week].to_dict() if not emo_matrix.empty else {}
        topic_row = topic_matrix.loc[target_week].to_dict() if not topic_matrix.empty else {}
        text_concat = "\n".join(texts)
        tokens_all = self.preprocessor.clean_text(text_concat).split()
        vocab_rich = len(set(tokens_all)) / max(len(tokens_all), 1)
        lens = [len(t.split()) for t in texts if t.split()]
        ling_var = float(pd.Series(lens).std() or 0.0) / max(float(pd.Series(lens).mean() or 1.0), 1.0)
        emotion_payload = dict(emotion_row)
        emotion_payload["_vocab_richness"] = float(vocab_rich)
        emotion_payload["_linguistic_variability"] = float(ling_var)
        baseline = self._get_baseline_manager(user_id)
        if not baseline.is_baseline_ready():
            baseline.update_baseline(emotion_payload, topic_row, target_week)
            baseline.save_baseline()
            logger.info("Baseline accumulating for %s (%s/%s weeks)", user_id, baseline.weeks_recorded, baseline.baseline_weeks)
            return {
                "status": "baseline_pending",
                "week_id": target_week,
                "emotion": emotion_payload,
                "topics": topic_row,
            }
        analyzer = DeviationAnalyzer(baseline)
        current_week_data = {
            "emotion": {k: v for k, v in emotion_payload.items() if not k.startswith("_")},
            "topics": topic_row,
            "text_concat": text_concat,
        }
        deviations = analyzer.compute_all_deviations(current_week_data)
        deviations["_baseline_topics"] = baseline.topic_baseline
        indicators = self.indicator_generator.generate_all_indicators(deviations)
        baseline.update_ema(emotion_payload, topic_row)
        baseline.save_baseline()
        record = {
            "week_id": target_week,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "indicators": indicators,
            "emotion": emotion_payload,
            "topics": topic_row,
        }
        self._append_weekly_result(user_id, record)
        logger.info("Weekly analysis complete for %s week %s AS=%.3f", user_id, target_week, indicators["avoidance_score"])
        return {"status": "ok", **record}

    def _append_weekly_result(self, user_id: str, payload: Dict[str, Any]) -> None:
        if self._store:
            self._store.append_weekly_result(user_id, payload)
            return
        path = self._weekly_results_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def get_user_history(self, user_id: str) -> pd.DataFrame:
        """
        Return a longitudinal table of weekly indicators.

        Args:
            user_id: User identifier.

        Returns:
            DataFrame indexed by week with AS/TSI/EVS columns.
        """
        if self._store:
            return self._store.build_indicator_dataframe(user_id)
        path = self._weekly_results_path(user_id)
        if not path.exists():
            return pd.DataFrame(columns=["week_id", "avoidance_score", "topic_suppression_index", "emotional_variability_score"])
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            obj = json.loads(line)
            ind = obj.get("indicators", {})
            rows.append(
                {
                    "week_id": obj.get("week_id"),
                    "avoidance_score": ind.get("avoidance_score"),
                    "topic_suppression_index": ind.get("topic_suppression_index"),
                    "emotional_variability_score": ind.get("emotional_variability_score"),
                    "flagged": ind.get("flagged"),
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index("week_id")
        return df
