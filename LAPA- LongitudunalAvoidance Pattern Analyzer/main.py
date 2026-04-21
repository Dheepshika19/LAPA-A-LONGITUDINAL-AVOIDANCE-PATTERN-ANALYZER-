"""
LAPA command-line entrypoint for training, evaluation, demo, and dashboard modes.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def train_mode(config_path: Path) -> None:
    """Fine-tune emotion model and train BERTopic on a text corpus."""
    from modules.emotion_classifier import EmotionClassifier
    from modules.topic_modeler import TopicModeler

    cfg = _load_config(config_path)
    logging.info("=== LAPA train mode ===")
    root = Path(cfg["data_paths"]["root"])
    emotion_dir = root / cfg["data_paths"]["emotion_model_dir"]
    clf = EmotionClassifier(str(emotion_dir), cfg)
    clf.fine_tune()
    tm = TopicModeler(cfg)
    try:
        from datasets import load_dataset

        sample = load_dataset("go_emotions", "raw", split="train[:2000]")
        texts = [r["text"] for r in sample]
    except Exception as exc:  # pragma: no cover - network dependent
        logging.warning("Could not load GoEmotions for topic training: %s", exc)
        texts = [
            "Family dinner reminded me how much I miss talking openly with my parents.",
            "Work has been overwhelming and I feel stretched thin every day.",
            "Doctor said my sleep should improve if I keep a routine.",
            "My partner and I finally had an honest conversation about boundaries.",
            "I want to understand myself better through journaling.",
            "Social events still make me anxious but I am trying small steps.",
        ] * 40
    tm.train(texts)
    logging.info("Training complete. Models saved under %s", cfg["data_paths"]["models"])


def evaluate_mode(config_path: Path) -> None:
    """Run lightweight evaluation and baseline comparisons."""
    from evaluation.evaluate import Evaluator
    from pipeline.controller import PipelineController

    cfg = _load_config(config_path)
    logging.info("=== LAPA evaluate mode ===")
    controller = PipelineController(str(config_path))
    evaluator = Evaluator(cfg)
    daic_full = Path(cfg["data_paths"]["root"]) / cfg["data_paths"]["daic_placeholder"]
    metrics = evaluator.evaluate_on_daic_woz(controller, str(daic_full))
    logging.info("DAIC-style metrics: %s", metrics)
    test_rows = [
        {"text": "I feel exhausted and hopeless every morning", "label": 1},
        {"text": "Today was productive and I enjoyed time with friends", "label": 0},
        {"text": "I am not sure about anything anymore", "label": 1},
        {"text": "Grateful for small wins and sunshine today", "label": 0},
    ] * 6
    evaluator.compare_with_baselines(test_rows)
    xs = [0.2, 0.35, 0.5, 0.62, 0.7]
    ys = [4, 6, 8, 11, 14]
    evaluator.plot_results(
        {
            "accuracy": [0.5, 0.55, 0.6, 0.65, 0.7],
            "loss": [0.8, 0.65, 0.55, 0.48, 0.4],
            "confusion_matrix": [[3, 1], [0, 4]],
            "scatter": (xs, ys),
        }
    )


def demo_mode(config_path: Path) -> None:
    """Simulated longitudinal journaling demo in the terminal."""
    from pipeline.controller import PipelineController

    cfg = _load_config(config_path)
    logging.info("=== LAPA interactive demo ===")
    controller = PipelineController(str(config_path))
    user = input("User id [demo_user]: ").strip() or "demo_user"
    start = datetime(2026, 1, 4)
    for w in range(8):
        week_start = start + timedelta(weeks=w)
        text = input(f"Week {w+1} journal ({week_start.date()}): ").strip()
        if not text:
            text = "I spent time journaling about my feelings and daily events."
        controller.process_entry(user, text, week_start.date().isoformat())
        hist = controller.get_user_history(user)
        logging.info("History tail:\n%s", hist.tail())


def dashboard_mode(config_path: Path) -> None:
    """Launch the Flask dashboard."""
    from dashboard.app import create_app

    cfg = _load_config(config_path)
    host = cfg.get("dashboard", {}).get("host", "127.0.0.1")
    port = int(cfg.get("dashboard", {}).get("port", 5000))
    app = create_app(str(config_path))
    logging.info("Starting LAPA dashboard on http://%s:%s", host, port)
    app.run(host=host, port=port, debug=False)


def main(argv: List[str] | None = None) -> int:
    """Parse CLI arguments and dispatch to the requested mode."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="LAPA — Longitudinal Avoidance Pattern Analyzer")
    parser.add_argument(
        "--mode",
        choices=["train", "evaluate", "demo", "dashboard"],
        required=True,
        help="Operational mode",
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).parent / "config" / "config.yaml"),
        help="Path to config.yaml",
    )
    args = parser.parse_args(argv)
    cfg_path = Path(args.config)
    if args.mode == "train":
        train_mode(cfg_path)
    elif args.mode == "evaluate":
        evaluate_mode(cfg_path)
    elif args.mode == "demo":
        demo_mode(cfg_path)
    elif args.mode == "dashboard":
        dashboard_mode(cfg_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
