"""
Quantifies departures from a user's established writing baseline.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict

from modules.baseline_manager import BaselineManager


class DeviationAnalyzer:
    """
    Computes topic suppression, emotional flattening, and lexical vagueness.
    """

    def __init__(self, baseline_manager: BaselineManager) -> None:
        """
        Args:
            baseline_manager: Longitudinal reference statistics for a user.
        """
        self._baseline = baseline_manager

    def compute_topic_suppression(
        self,
        current_topics: Dict[str, float],
        baseline_topics: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Measure relative drops in domain frequency versus baseline.

        Args:
            current_topics: Normalized domain counts for the active week.
            baseline_topics: Established baseline domain profile.

        Returns:
            Per-domain suppression scores in ``[0, 1]``.
        """
        out: Dict[str, float] = {}
        for topic, base_freq in baseline_topics.items():
            cur = float(current_topics.get(topic, 0.0))
            base = float(base_freq)
            if base <= 1e-6:
                sup = 0.0
            else:
                sup = max(0.0, base - cur) / base
            out[topic] = float(min(1.0, sup))
        return out

    def compute_emotional_flattening(
        self,
        current_emotion: Dict[str, float],
        baseline_emotion: Dict[str, float],
    ) -> float:
        """
        Compare coefficient-of-variation shrinkage across emotion categories.

        Args:
            current_emotion: Mean weekly probabilities.
            baseline_emotion: Baseline weekly probabilities.

        Returns:
            Normalized flattening magnitude in ``[0, 1]``.
        """

        def _cv(dist: Dict[str, float]) -> float:
            vals = [float(v) for v in dist.values() if isinstance(v, (int, float))]
            if not vals:
                return 0.0
            mean = sum(vals) / len(vals)
            if mean <= 1e-9:
                return 0.0
            var = sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1)
            return math.sqrt(max(var, 0.0)) / mean

        base_cv = _cv(baseline_emotion)
        cur_cv = _cv(current_emotion)
        raw = max(0.0, base_cv - cur_cv)
        denom = max(base_cv, 1e-3)
        return float(min(1.0, raw / denom))

    def compute_linguistic_vagueness(self, text: str) -> float:
        """
        Heuristic density of hedging and vague quantifiers.

        Args:
            text: Raw journal entry.

        Returns:
            Score in ``[0, 1]`` based on rate per token.
        """
        if not text or not str(text).strip():
            return 0.0
        lowered = str(text).lower()
        tokens = re.findall(r"[a-zA-Z']+", lowered)
        n = max(len(tokens), 1)
        hedges = [
            "maybe",
            "perhaps",
            "kind of",
            "sort of",
            "possibly",
            "might",
            "could be",
            "somewhat",
        ]
        vague = ["some", "few", "many", "several", "someone", "something", "somewhere"]
        hits = 0
        for phrase in hedges:
            hits += len(re.findall(rf"\b{re.escape(phrase)}\b", lowered))
        for w in vague:
            hits += len(re.findall(rf"\b{re.escape(w)}\b", lowered))
        rate = hits / float(n)
        return float(min(1.0, rate * 4.0))

    def compute_all_deviations(self, current_week_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bundle all deviation signals for downstream indicators.

        Args:
            current_week_data: Must include ``emotion``, ``topics``, and ``text_concat``.

        Returns:
            Structured dictionary with suppression map and scalar cues.
        """
        cur_emo: Dict[str, float] = dict(current_week_data.get("emotion", {}))
        cur_top: Dict[str, float] = dict(current_week_data.get("topics", {}))
        text_cat = str(current_week_data.get("text_concat", ""))
        base_emo = self._baseline.emotion_baseline
        base_top = self._baseline.topic_baseline
        suppression = self.compute_topic_suppression(cur_top, base_top)
        flat = self.compute_emotional_flattening(cur_emo, base_emo)
        vague = self.compute_linguistic_vagueness(text_cat)
        return {
            "topic_suppression": suppression,
            "emotional_flattening": flat,
            "linguistic_vagueness": vague,
        }
