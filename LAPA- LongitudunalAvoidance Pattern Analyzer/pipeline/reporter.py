"""
Human-readable reporting helpers for clinicians and dashboards.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


class Reporter:
    """
    Converts numeric indicators into structured clinical narratives.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Args:
            config: Global configuration for thresholds and copy tone.
        """
        self._config = config
        self._threshold = float(config.get("avoidance_threshold", 0.65))
        self._watch = float(config.get("watch_threshold_low", 0.4))

    def generate_weekly_report(self, user_id: str, week_id: str, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        Package weekly indicators with interpretation strings.

        Args:
            user_id: Subject identifier.
            week_id: ISO week label.
            indicators: Output of :meth:`IndicatorGenerator.generate_all_indicators`.

        Returns:
            Nested dictionary suitable for JSON APIs.
        """
        as_score = float(indicators.get("avoidance_score", 0.0))
        tsi = float(indicators.get("topic_suppression_index", 0.0))
        evs = float(indicators.get("emotional_variability_score", 0.0))
        flagged = bool(indicators.get("flagged", False))

        def band(value: float) -> str:
            if value < self._watch:
                return "Within typical expressive variation for this person."
            if value < self._threshold:
                return "Mild shift relative to baseline — continue longitudinal monitoring."
            return "Notable departure from baseline — consider collaborative review in clinical context."

        interpretations = {
            "avoidance_score": band(as_score),
            "topic_suppression_index": band(tsi),
            "emotional_variability_score": band(evs),
        }
        flag_block = {
            "active": flagged,
            "detail": indicators.get("flag_reason", ""),
        }
        return {
            "user_id": user_id,
            "week_id": week_id,
            "indicators": {
                "avoidance_score": as_score,
                "topic_suppression_index": tsi,
                "emotional_variability_score": evs,
            },
            "interpretations": interpretations,
            "flag": flag_block,
            "topic_suppression_detail": indicators.get("topic_suppression_detail", {}),
        }

    def generate_longitudinal_summary(self, user_id: str, history: pd.DataFrame) -> Dict[str, Any]:
        """
        Summarize multi-week trends and sustained elevations.

        Args:
            user_id: Subject identifier.
            history: Indicator history from :meth:`PipelineController.get_user_history`.

        Returns:
            Dictionary with simple trend labels and alert metadata.
        """
        if history is None or history.empty:
            return {"user_id": user_id, "trends": {}, "sustained_alert": False}
        tail = history.tail(8)
        trends: Dict[str, str] = {}
        sustained = False

        def trend(series: pd.Series) -> str:
            vals = [float(x) for x in series.dropna().tolist()]
            if len(vals) < 2:
                return "stable"
            diff = vals[-1] - vals[0]
            if diff > 0.05:
                return "increasing"
            if diff < -0.05:
                return "decreasing"
            return "stable"

        for col in ["avoidance_score", "topic_suppression_index", "emotional_variability_score"]:
            if col in tail.columns:
                trends[col] = trend(tail[col])
        for col in ["avoidance_score", "topic_suppression_index", "emotional_variability_score"]:
            if col not in tail.columns:
                continue
            highs = [float(x) >= self._threshold for x in tail[col].tolist() if pd.notna(x)]
            if sum(highs) >= 3:
                sustained = True
        return {
            "user_id": user_id,
            "trends": trends,
            "sustained_alert": sustained,
            "window_weeks": int(len(tail)),
        }
