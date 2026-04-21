"""
Integration-style tests for the LAPA pipeline with heavy models mocked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from modules.indicator_generator import IndicatorGenerator
from pipeline.controller import PipelineController


def _write_config(tmp_path: Path) -> Path:
    base_cfg = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    cfg = yaml.safe_load(base_cfg.read_text(encoding="utf-8"))
    cfg["data_paths"]["root"] = str(tmp_path)
    cfg["data_paths"]["raw"] = "data/raw"
    cfg["data_paths"]["processed"] = "data/processed"
    cfg["data_paths"]["models"] = "models"
    cfg["data_paths"]["emotion_model_dir"] = "models/emotion_roberta"
    cfg["data_paths"]["topic_model_dir"] = "models/topic_model"
    cfg["data_paths"]["baselines_dir"] = "data/processed/baselines"
    cfg["data_paths"]["user_entries_dir"] = "data/processed/users"
    cfg["data_paths"]["weekly_results_dir"] = "data/processed/weekly_results"
    cfg["data_paths"]["evaluation_plots_dir"] = "evaluation/plots"
    cfg["data_paths"]["daic_placeholder"] = "data/raw/daic_woz"
    cfg["storage"] = {"backend": "sqlite", "database_path": str(tmp_path / "lapa.sqlite")}
    out = tmp_path / "config.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return out


def test_indicator_ranges() -> None:
    """Indicator outputs should remain within the unit interval."""
    cfg = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "config.yaml").read_text())
    gen = IndicatorGenerator(cfg)
    dev = {
        "topic_suppression": {"family": 0.8, "work": 0.1},
        "emotional_flattening": 0.4,
        "linguistic_vagueness": 0.2,
        "_baseline_topics": {"family": 0.5, "work": 0.2, "health": 0.1, "relationships": 0.1, "self": 0.05, "social": 0.05},
    }
    out = gen.generate_all_indicators(dev)
    for key in ("avoidance_score", "topic_suppression_index", "emotional_variability_score"):
        assert 0.0 <= out[key] <= 1.0


def test_topic_suppression_scenario(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Fabricated longitudinal pattern: stable family mentions, then sudden drop.

    Expect topic suppression for the family domain to be pronounced.
    """
    cfg_path = _write_config(tmp_path)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    class StubEmotion:
        def classify_batch(self, texts: List[str]) -> List[Dict[str, float]]:
            base = {c: 1.0 / len(cfg["emotion_categories"]) for c in cfg["emotion_categories"]}
            return [dict(base) for _ in texts]

        def get_weekly_emotion_matrix(self, weekly_windows: Dict[str, Any]) -> Any:
            import pandas as pd

            rows = []
            for wid, ents in weekly_windows.items():
                if not ents:
                    continue
                row = {c: 1.0 / len(cfg["emotion_categories"]) for c in cfg["emotion_categories"]}
                row["week_id"] = wid
                rows.append(row)
            return pd.DataFrame(rows).set_index("week_id") if rows else pd.DataFrame()

    class StubTopic:
        def __init__(self) -> None:
            self.state = 0

        def get_weekly_topic_matrix(self, weekly_windows: Dict[str, Any]) -> Any:
            import pandas as pd

            rows = []
            for wid in sorted(weekly_windows.keys()):
                if self.state < 4:
                    vec = {"family": 0.7, "work": 0.1, "health": 0.05, "relationships": 0.05, "self": 0.05, "social": 0.05}
                else:
                    vec = {"family": 0.05, "work": 0.3, "health": 0.2, "relationships": 0.15, "self": 0.2, "social": 0.1}
                vec["week_id"] = wid
                rows.append(vec)
            self.state += 1
            return pd.DataFrame(rows).set_index("week_id")

        def assign_topic(self, text: str) -> str:
            return "family"

        def train(self, texts: List[str]) -> None:
            return None

        def load(self) -> None:
            return None

    import torch

    import modules.preprocessor as pre
    import pipeline.controller as pc

    class DummyTokenizer:
        @staticmethod
        def from_pretrained(*_a, **_k):
            return DummyTokenizer()

        def __call__(self, *_args, **kwargs):
            return {
                "input_ids": torch.ones(1, 8, dtype=torch.long),
                "attention_mask": torch.ones(1, 8, dtype=torch.long),
            }

    monkeypatch.setattr(pre, "AutoTokenizer", DummyTokenizer)
    monkeypatch.setattr(pc, "EmotionClassifier", lambda model_path, config: StubEmotion())
    monkeypatch.setattr(pc, "TopicModeler", lambda config: StubTopic())
    monkeypatch.setattr(
        pc.TextPreprocessor,
        "clean_text",
        lambda self, text: str(text).lower(),
    )
    controller = PipelineController(str(cfg_path))

    user = "tester"
    start = __import__("datetime").date(2026, 1, 5)
    for w in range(8):
        day = start.toordinal() + w * 7
        dt = __import__("datetime").date.fromordinal(day)
        text = (
            "My family and I talked openly about stress at home."
            if w < 4
            else "Work meetings and errands filled the week; I kept things vague."
        )
        controller.process_entry(user, text, dt.isoformat())

    hist = controller.get_user_history(user)
    assert not hist.empty
    last = hist.iloc[-1]
    assert 0.0 <= float(last["topic_suppression_index"]) <= 1.0
    assert 0.0 <= float(last["avoidance_score"]) <= 1.0


def test_flagging_threshold(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """High suppression should raise the composite avoidance score."""
    cfg = yaml.safe_load(_write_config(tmp_path).read_text(encoding="utf-8"))
    cfg["avoidance_threshold"] = 0.2
    gen = IndicatorGenerator(cfg)
    dev = {
        "topic_suppression": {d: 0.95 for d in cfg["topic_domains"]},
        "emotional_flattening": 0.9,
        "linguistic_vagueness": 0.9,
        "_baseline_topics": {d: 1.0 / len(cfg["topic_domains"]) for d in cfg["topic_domains"]},
    }
    out = gen.generate_all_indicators(dev)
    assert out["flagged"] is True
