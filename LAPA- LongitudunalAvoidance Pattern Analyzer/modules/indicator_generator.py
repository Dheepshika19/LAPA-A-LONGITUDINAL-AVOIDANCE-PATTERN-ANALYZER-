"""
Maps deviation signals to clinician-facing longitudinal indicators.
"""

from __future__ import annotations

from typing import Any, Dict


class IndicatorGenerator:
    """
    Produces AS / TSI / EVS and simple decision-support flags.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Args:
            config: Must include ``as_weights`` and ``avoidance_threshold``.
        """
        self._config = config
        weights = dict(config.get("as_weights", {}))
        self.as_weights = {
            "topic": float(weights.get("topic", 0.4)),
            "emotion": float(weights.get("emotion", 0.4)),
            "vagueness": float(weights.get("vagueness", 0.2)),
        }
        total = sum(self.as_weights.values()) or 1.0
        self.as_weights = {k: v / total for k, v in self.as_weights.items()}
        self.threshold = float(config.get("avoidance_threshold", 0.65))

    def compute_avoidance_score(self, deviations: Dict[str, Any]) -> float:
        """
        Weighted fusion of topic, emotion, and vagueness deviations.

        Args:
            deviations: Output of :meth:`DeviationAnalyzer.compute_all_deviations`.

        Returns:
            Avoidance score in ``[0, 1]``.
        """
        ts = deviations.get("topic_suppression", {}) or {}
        base_top: Dict[str, float] = deviations.get("_baseline_topics") or self._placeholder_baseline_topics()
        tsi = self.compute_topic_suppression_index(ts, base_top)
        flat = float(deviations.get("emotional_flattening", 0.0))
        vague = float(deviations.get("linguistic_vagueness", 0.0))
        emo_component = min(1.0, 0.5 * flat + 0.5 * vague)
        score = (
            self.as_weights["topic"] * tsi
            + self.as_weights["emotion"] * emo_component
            + self.as_weights["vagueness"] * vague
        )
        return float(max(0.0, min(1.0, score)))

    def _placeholder_baseline_topics(self) -> Dict[str, float]:
        """Uniform prior used only inside AS fusion when topics dict is empty."""
        doms = list(self._config.get("topic_domains", []))
        if not doms:
            return {}
        u = 1.0 / len(doms)
        return {d: u for d in doms}

    def compute_topic_suppression_index(
        self,
        topic_suppressions: Dict[str, float],
        baseline_topics: Dict[str, float],
    ) -> float:
        """
        Frequency-weighted mean suppression across domains.

        Args:
            topic_suppressions: Per-domain suppression magnitudes.
            baseline_topics: Baseline domain proportions for weighting.

        Returns:
            Topic suppression index in ``[0, 1]``.
        """
        if not topic_suppressions:
            return 0.0
        weights = []
        values = []
        for dom, val in topic_suppressions.items():
            w = float(baseline_topics.get(dom, 0.0))
            weights.append(w)
            values.append(float(val))
        sw = sum(weights)
        if sw <= 1e-9:
            return float(sum(values) / max(len(values), 1))
        num = sum(w * v for w, v in zip(weights, values))
        return float(max(0.0, min(1.0, num / sw)))

    def compute_emotional_variability_score(self, emotion_flattening: float) -> float:
        """
        Translate flattening into a variability-centric score.

        Args:
            emotion_flattening: Higher means more flattening vs baseline.

        Returns:
            Emotional variability score in ``[0, 1]`` where higher reflects
            reduced healthy variability (clinician-facing risk direction).
        """
        return float(max(0.0, min(1.0, emotion_flattening)))

    def generate_all_indicators(self, deviations: Dict[str, Any]) -> Dict[str, Any]:
        """
        Produce final numeric indicators and textual flag metadata.

        Args:
            deviations: Bundle from :meth:`DeviationAnalyzer.compute_all_deviations`.

        Returns:
            Dictionary with scores, booleans, and human-readable reasons.
        """
        ts = deviations.get("topic_suppression", {}) or {}
        baseline_topics = dict(deviations.get("_baseline_topics") or self._placeholder_baseline_topics())
        deviations_for_as = dict(deviations)
        deviations_for_as["_baseline_topics"] = baseline_topics
        tsi = self.compute_topic_suppression_index(ts, baseline_topics)
        flat = float(deviations.get("emotional_flattening", 0.0))
        evs = self.compute_emotional_variability_score(flat)
        as_score = self.compute_avoidance_score(deviations_for_as)
        flagged = as_score >= self.threshold
        reasons = []
        if flagged:
            reasons.append(
                f"Avoidance score {as_score:.2f} meets or exceeds threshold {self.threshold:.2f}."
            )
        if tsi >= self.threshold:
            reasons.append("Topic suppression index is elevated relative to baseline frequencies.")
        if evs >= self.threshold:
            reasons.append("Emotional variability score suggests reduced expressive range.")
        flag_reason = " ".join(reasons) if reasons else "Within expected longitudinal variation."
        return {
            "avoidance_score": float(as_score),
            "topic_suppression_index": float(tsi),
            "emotional_variability_score": float(evs),
            "flagged": bool(flagged or tsi >= self.threshold or evs >= self.threshold),
            "flag_reason": flag_reason,
            "topic_suppression_detail": ts,
        }
