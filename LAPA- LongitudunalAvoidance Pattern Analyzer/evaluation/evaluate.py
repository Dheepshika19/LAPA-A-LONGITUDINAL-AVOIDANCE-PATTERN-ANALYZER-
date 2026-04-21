"""
Evaluation harness comparing LAPA to lightweight baselines.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import classification_report
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class Evaluator:
    """
    Correlation-style checks, baseline comparisons, and diagnostic plots.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Args:
            config: Global configuration dictionary.
        """
        self._config = config
        root = Path(config["data_paths"]["root"])
        rel = Path(config["data_paths"]["evaluation_plots_dir"])
        self._plot_dir = rel if rel.is_absolute() else root / rel
        self._plot_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_on_daic_woz(self, pipeline: Any, data_path: str) -> Dict[str, Any]:
        """
        Run LAPA on DAIC-WOZ-style transcripts when available.

        Args:
            pipeline: Instance with ``process_entry`` / ``get_user_history``.
            data_path: Directory or CSV with ``text``, ``participant_id``, ``phq8`` columns.

        Returns:
            Metrics dictionary including Pearson correlation when computable.
        """
        path = Path(data_path)
        if not path.exists():
            logger.warning("DAIC-WOZ data not found at %s — generating synthetic demo rows.", path)
            df = self._synthetic_daic()
        elif path.is_dir():
            csv_candidates = list(path.glob("*.csv"))
            if not csv_candidates:
                df = self._synthetic_daic()
            else:
                df = pd.read_csv(csv_candidates[0])
        else:
            df = pd.read_csv(path)
        scores: List[float] = []
        labels: List[float] = []
        for _, row in df.iterrows():
            user = str(row.get("participant_id", "anon"))
            text = str(row.get("text", ""))
            date = str(row.get("date", "2026-01-01"))
            pipeline.process_entry(user, text, date)
            hist = pipeline.get_user_history(user)
            if hist.empty:
                continue
            scores.append(float(hist["avoidance_score"].iloc[-1]))
            labels.append(float(row.get("phq8", 0)))
        if len(scores) < 2:
            return {"status": "insufficient_data", "n": len(scores)}
        corr = float(np.corrcoef(scores, labels)[0, 1]) if len(set(labels)) > 1 else 0.0
        y_bin = [1 if y >= 10 else 0 for y in labels]
        y_hat = [1 if s >= float(self._config.get("avoidance_threshold", 0.65)) else 0 for s in scores]
        print("DAIC-WOZ proxy evaluation")
        print(classification_report(y_bin, y_hat, zero_division=0))
        return {"pearson_r": corr, "n": len(scores)}

    @staticmethod
    def _synthetic_daic() -> pd.DataFrame:
        rows = []
        for i in range(12):
            phq = 5 + (i % 5)
            rows.append(
                {
                    "participant_id": f"p{i}",
                    "text": "I feel tired and empty" * (1 + i // 4),
                    "date": f"2026-01-{i+1:02d}",
                    "phq8": phq,
                }
            )
        return pd.DataFrame(rows)

    def compare_with_baselines(self, test_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Compare LAPA-style scores against four lightweight baselines.

        Args:
            test_data: List of dicts with ``text`` and binary ``label`` keys.

        Returns:
            Printed and returned comparison table.
        """
        texts = [d["text"] for d in test_data]
        y = np.array([int(d["label"]) for d in test_data])
        vader = SentimentIntensityAnalyzer()
        vader_scores = np.array([vader.polarity_scores(t)["compound"] for t in texts])
        keywords = ["sad", "hopeless", "empty", "tired", "anxious"]
        key_scores = np.array([sum(k in t.lower() for k in keywords) / len(keywords) for t in texts])
        # pseudo BERT embedding via hashing bag-of-words for demo portability
        bow = self._hash_bow(texts)
        bert_like = LogisticRegression(max_iter=200).fit(bow, y).predict_proba(bow)[:, 1]
        lstm_like = cosine_similarity(bow, bow.mean(axis=0, keepdims=True)).ravel()
        rows = []
        for name, scores in [
            ("VADER sentiment", vader_scores),
            ("Keyword density", key_scores),
            ("Pseudo-BERT session", bert_like),
            ("Pseudo-BiLSTM longitudinal", lstm_like),
        ]:
            preds = (scores >= np.median(scores)).astype(int)
            report = classification_report(y, preds, output_dict=True, zero_division=0)
            rows.append({"model": name, "f1": float(report["weighted avg"]["f1-score"])})
        df = pd.DataFrame(rows)
        print(df.to_string(index=False))
        return df

    @staticmethod
    def _hash_bow(texts: List[str], dim: int = 64) -> np.ndarray:
        mat = np.zeros((len(texts), dim))
        for i, t in enumerate(texts):
            for tok in t.lower().split():
                mat[i, hash(tok) % dim] += 1.0
        row_sums = mat.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1.0
        return mat / row_sums

    def plot_results(self, results: Dict[str, Any]) -> None:
        """
        Persist diagnostic figures for training / evaluation summaries.

        Args:
            results: Dictionary containing optional loss/accuracy series and matrices.
        """
        acc = results.get("accuracy", [])
        loss = results.get("loss", [])
        if acc:
            plt.figure(figsize=(6, 4))
            plt.plot(acc, label="accuracy")
            plt.xlabel("Step")
            plt.ylabel("Accuracy")
            plt.legend()
            plt.tight_layout()
            plt.savefig(self._plot_dir / "accuracy_trend.png")
            plt.close()
        if loss:
            plt.figure(figsize=(6, 4))
            plt.plot(loss, color="orange", label="loss")
            plt.xlabel("Step")
            plt.ylabel("Loss")
            plt.legend()
            plt.tight_layout()
            plt.savefig(self._plot_dir / "loss_trend.png")
            plt.close()
        cm = results.get("confusion_matrix")
        if cm is not None:
            plt.figure(figsize=(4, 3))
            sns.heatmap(cm, annot=True, fmt="d", cmap="Blues")
            plt.ylabel("True")
            plt.xlabel("Pred")
            plt.tight_layout()
            plt.savefig(self._plot_dir / "confusion_matrix.png")
            plt.close()
        scatter = results.get("scatter")
        if scatter:
            xs, ys = scatter
            plt.figure(figsize=(5, 4))
            plt.scatter(xs, ys, alpha=0.7)
            plt.xlabel("Avoidance score")
            plt.ylabel("PHQ-8 proxy")
            plt.tight_layout()
            plt.savefig(self._plot_dir / "indicator_correlation.png")
            plt.close()
        meta_path = self._plot_dir / "results_meta.json"
        meta_path.write_text(json.dumps({k: str(v) for k, v in results.items()}, indent=2), encoding="utf-8")
        logger.info("Saved evaluation plots to %s", self._plot_dir)
