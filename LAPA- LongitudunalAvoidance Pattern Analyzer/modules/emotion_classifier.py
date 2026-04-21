"""
RoBERTa-based emotion modeling with GoEmotions fine-tuning support.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from datasets import Dataset, load_dataset
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    RobertaTokenizerFast,
    get_linear_schedule_with_warmup,
)

logger = logging.getLogger(__name__)


def _go_emotions_label_order() -> List[str]:
    """Canonical label order for the public GoEmotions multilabel split."""
    return [
        "admiration",
        "amusement",
        "anger",
        "annoyance",
        "approval",
        "caring",
        "confusion",
        "curiosity",
        "desire",
        "disappointment",
        "disapproval",
        "disgust",
        "embarrassment",
        "excitement",
        "fear",
        "gratitude",
        "grief",
        "joy",
        "love",
        "nervousness",
        "optimism",
        "pride",
        "realization",
        "relief",
        "remorse",
        "sadness",
        "surprise",
        "neutral",
    ]


def _label_to_category() -> Dict[str, str]:
    """Map each GoEmotions label to one of six clinical buckets."""
    m: Dict[str, str] = {}
    for lab in _go_emotions_label_order():
        low = lab.lower()
        if low in {"fear", "nervousness", "embarrassment"}:
            m[lab] = "fear"
        elif low in {"sadness", "grief", "remorse", "disappointment"}:
            m[lab] = "sadness"
        elif low in {"anger", "annoyance", "disapproval", "disgust"}:
            m[lab] = "anger"
        elif low in {
            "joy",
            "amusement",
            "excitement",
            "love",
            "gratitude",
            "pride",
            "optimism",
            "relief",
            "admiration",
            "approval",
            "desire",
            "caring",
        }:
            m[lab] = "joy"
        elif low in {"surprise", "confusion", "curiosity", "realization"}:
            m[lab] = "surprise"
        else:
            m[lab] = "neutral"
    return m


class EmotionClassifier:
    """
    Multilabel emotion classifier backed by RoBERTa.

    Supports fine-tuning on GoEmotions and maps 28 labels into six
    clinician-facing categories from configuration.
    """

    def __init__(self, model_path: Optional[str], config: Dict[str, Any]) -> None:
        """
        Load tokenizer/model from disk or a public fallback checkpoint.

        Args:
            model_path: Directory with a saved classifier, if available.
            config: Global configuration dictionary.
        """
        self._config = config
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._categories: List[str] = list(config.get("emotion_categories", []))
        self._max_len = int(config.get("max_seq_length", 512))
        root = Path(config["data_paths"]["root"])
        resolved = Path(model_path) if model_path else root / config["data_paths"]["emotion_model_dir"]
        self._model_dir = resolved
        fallback = config.get("emotion_pretrained_fallback", "SamLowe/roberta-base-go_emotions")
        base_name = config.get("roberta_model", "roberta-base")
        load_dir = str(resolved) if self._has_checkpoint(resolved) else fallback
        logger.info("EmotionClassifier loading weights from %s", load_dir)
        self._tokenizer: RobertaTokenizerFast = AutoTokenizer.from_pretrained(load_dir)
        self._model = AutoModelForSequenceClassification.from_pretrained(load_dir)
        self._model.to(self._device)
        self._model.eval()
        self._label_names = self._resolve_label_names(load_dir)
        self._aggregator = self._build_aggregator_matrix(self._label_names)
        if not self._has_checkpoint(resolved):
            logger.warning(
                "No local emotion checkpoint at %s — using fallback %s",
                resolved,
                fallback,
            )

    @staticmethod
    def _has_checkpoint(path: Path) -> bool:
        return path.exists() and (
            (path / "model.safetensors").exists() or (path / "pytorch_model.bin").exists()
        )

    def _resolve_label_names(self, load_dir: str) -> List[str]:
        id2label = self._model.config.id2label  # type: ignore[attr-defined]
        if isinstance(id2label, dict) and id2label:
            def _sort_key(k: Union[int, str]) -> tuple[int, str]:
                try:
                    return int(str(k)), ""
                except ValueError:
                    return 10**9, str(k)

            keys = sorted(id2label.keys(), key=_sort_key)
            return [str(id2label[k]) for k in keys]
        return _go_emotions_label_order()

    def _build_aggregator_matrix(self, label_names: List[str]) -> torch.Tensor:
        """Shape [6, num_labels] to map logits/probs into six categories."""
        lab2cat = _label_to_category()
        mat = torch.zeros((len(self._categories), len(label_names)), dtype=torch.float32)
        for j, name in enumerate(label_names):
            cat = lab2cat.get(str(name), "neutral")
            if cat in self._categories:
                i = self._categories.index(cat)
                mat[i, j] = 1.0
            else:
                mat[self._categories.index("neutral"), j] = 1.0
        return mat.to(self._device)

    def fine_tune(self, dataset: Optional[str] = None) -> None:
        """
        Fine-tune RoBERTa on GoEmotions with class-balanced BCE targets.

        Args:
            dataset: Optional HF dataset name; defaults to config ``emotion_dataset``.
        """
        ds_name = dataset or str(self._config.get("emotion_dataset", "go_emotions"))
        logger.info("Starting emotion fine-tune on %s", ds_name)
        raw = load_dataset(ds_name, "raw")
        train_rows = raw["train"]
        max_samples = int(self._config.get("max_train_samples", 8000))
        if max_samples > 0:
            train_rows = train_rows.select(range(min(max_samples, len(train_rows))))
        texts = [r["text"] for r in train_rows]
        label_matrix = np.zeros((len(texts), len(self._label_names)), dtype=np.float32)
        for i, row in enumerate(train_rows):
            for idx in row["labels"]:
                if idx < label_matrix.shape[1]:
                    label_matrix[i, idx] = 1.0
        pos_counts = label_matrix.sum(axis=0)
        neg_counts = len(label_matrix) - pos_counts
        pos_weight = np.where(pos_counts > 0, neg_counts / np.maximum(pos_counts, 1.0), 1.0)
        pos_weight_t = torch.tensor(pos_weight, dtype=torch.float32, device=self._device)

        encodings = self._tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=self._max_len,
            return_tensors="pt",
        )
        torch_ds = torch.utils.data.TensorDataset(
            encodings["input_ids"],
            encodings["attention_mask"],
            torch.tensor(label_matrix, dtype=torch.float32),
        )
        batch_size = int(self._config.get("batch_size", 32))
        loader = DataLoader(torch_ds, batch_size=batch_size, shuffle=True)

        self._model.train()
        lr = float(self._config.get("learning_rate", 2e-5))
        epochs = int(self._config.get("epochs", 10))
        optimizer = torch.optim.AdamW(self._model.parameters(), lr=lr, weight_decay=0.01)
        total_steps = len(loader) * epochs
        warmup_ratio = float(self._config.get("warmup_ratio", 0.06))
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            num_warmup_steps=int(total_steps * warmup_ratio),
            num_training_steps=total_steps,
        )
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight_t)
        patience = int(self._config.get("early_stopping_patience", 2))
        best_loss = float("inf")
        stall = 0

        for epoch in range(epochs):
            running = 0.0
            for batch in loader:
                input_ids, attention, labels = batch
                input_ids = input_ids.to(self._device)
                attention = attention.to(self._device)
                labels = labels.to(self._device)
                optimizer.zero_grad()
                outputs = self._model(input_ids=input_ids, attention_mask=attention)
                logits = outputs.logits
                loss = loss_fn(logits, labels)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                running += float(loss.item())
            avg_loss = running / max(len(loader), 1)
            logger.info("Emotion train epoch %s/%s loss=%.4f", epoch + 1, epochs, avg_loss)
            if avg_loss + 1e-4 < best_loss:
                best_loss = avg_loss
                stall = 0
                self._save_checkpoint()
            else:
                stall += 1
                if stall >= patience:
                    logger.info("Early stopping triggered at epoch %s", epoch + 1)
                    break
        self._model.eval()

    def _save_checkpoint(self) -> None:
        out_dir = Path(self._config["data_paths"]["emotion_model_dir"])
        if not out_dir.is_absolute():
            out_dir = Path(self._config["data_paths"]["root"]) / out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        self._model.save_pretrained(out_dir)
        self._tokenizer.save_pretrained(out_dir)
        meta = {"label_names": self._label_names}
        (out_dir / "lapa_emotion_meta.json").write_text(json.dumps(meta), encoding="utf-8")
        logger.info("Saved emotion checkpoint to %s", out_dir)

    def classify(self, text: str) -> Dict[str, float]:
        """
        Return six-way probability distribution for a single entry.

        Args:
            text: Raw journal text.

        Returns:
            Mapping of category -> probability (sums to ~1).
        """
        return self.classify_batch([text])[0]

    def classify_batch(self, texts: List[str]) -> List[Dict[str, float]]:
        """
        Batched inference for journal entries.

        Args:
            texts: Journal strings (empty strings are handled gracefully).

        Returns:
            List of probability dictionaries aligned with ``texts``.
        """
        cleaned = [t if isinstance(t, str) else str(t) for t in texts]
        if not cleaned:
            return []
        enc = self._tokenizer(
            cleaned,
            truncation=True,
            padding=True,
            max_length=self._max_len,
            return_tensors="pt",
        )
        enc = {k: v.to(self._device) for k, v in enc.items()}
        self._model.eval()
        with torch.no_grad():
            logits = self._model(**enc).logits
            probs = torch.sigmoid(logits)
            mapped = probs @ self._aggregator.T
            mapped = mapped / torch.clamp(mapped.sum(dim=1, keepdim=True), min=1e-6)
        out: List[Dict[str, float]] = []
        for row in mapped.cpu().numpy():
            vals = {cat: float(row[i]) for i, cat in enumerate(self._categories)}
            out.append(vals)
        return out

    def get_weekly_emotion_matrix(self, weekly_windows: Dict[str, List[Dict[str, Any]]]) -> pd.DataFrame:
        """
        Aggregate classifier outputs into a week-by-emotion matrix.

        Args:
            weekly_windows: Output of :meth:`TextPreprocessor.segment_to_weekly_windows`.

        Returns:
            DataFrame indexed by week with mean probabilities per emotion category.
        """
        rows: List[Dict[str, Any]] = []
        for week_id in sorted(weekly_windows.keys()):
            texts = [w.get("text", "") for w in weekly_windows[week_id]]
            if not texts:
                continue
            batch = self.classify_batch(texts)
            mean_vec = {c: float(np.mean([b[c] for b in batch])) for c in self._categories}
            mean_vec["week_id"] = week_id
            rows.append(mean_vec)
        if not rows:
            return pd.DataFrame(columns=["week_id"] + self._categories)
        df = pd.DataFrame(rows).set_index("week_id")
        return df
