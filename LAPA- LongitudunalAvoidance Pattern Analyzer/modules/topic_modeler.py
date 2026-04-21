"""
BERTopic-based thematic modeling with clinical domain mapping.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from bertopic import BERTopic
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer
from umap import UMAP

logger = logging.getLogger(__name__)


class TopicModeler:
    """
    Learns journal topics with BERTopic and projects them into six domains.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Configure embedding, UMAP, and HDBSCAN models from YAML settings.

        Args:
            config: Loaded configuration dictionary.
        """
        self._config = config
        self._domains: List[str] = list(config.get("topic_domains", []))
        embed_name = config.get("bertopic_embedding_model", "all-MiniLM-L6-v2")
        self._embedding_model = SentenceTransformer(embed_name)
        umap_neighbors = int(config.get("umap_neighbors", 10))
        umap_components = int(config.get("umap_components", 5))
        min_cluster = int(config.get("hdbscan_min_cluster", 10))
        self._umap_model = UMAP(
            n_neighbors=umap_neighbors,
            n_components=umap_components,
            min_dist=0.0,
            metric="cosine",
            random_state=42,
        )
        self._hdbscan_model = HDBSCAN(
            min_cluster_size=min_cluster,
            metric="euclidean",
            cluster_selection_method="eom",
            prediction_data=True,
        )
        self._topic_model: Optional[BERTopic] = None
        self._domain_seeds = self._build_domain_seeds()

    @staticmethod
    def _build_domain_seeds() -> Dict[str, List[str]]:
        """Lexical anchors for mapping noisy keywords to domains."""
        return {
            "family": ["family", "parent", "mother", "father", "sibling", "child", "home", "mom", "dad"],
            "work": ["work", "job", "boss", "office", "career", "deadline", "meeting", "salary", "project"],
            "health": ["health", "doctor", "pain", "sleep", "exercise", "sick", "medical", "therapy", "body"],
            "relationships": ["partner", "friend", "marriage", "love", "breakup", "dating", "spouse", "trust"],
            "self": ["myself", "identity", "goals", "growth", "values", "purpose", "self", "journal", "mind"],
            "social": ["social", "party", "community", "people", "group", "event", "conversation", "lonely"],
        }

    def _model_dir(self) -> Path:
        root = Path(self._config["data_paths"]["root"])
        rel = Path(self._config["data_paths"]["topic_model_dir"])
        return rel if rel.is_absolute() else root / rel

    def train(self, texts: List[str]) -> None:
        """
        Fit BERTopic on all journal texts and persist the model directory.

        Args:
            texts: Corpus of cleaned or raw journal strings.
        """
        corpus = [t for t in texts if isinstance(t, str) and t.strip()]
        if len(corpus) < max(self._hdbscan_model.min_cluster_size, 5):  # type: ignore[attr-defined]
            logger.warning(
                "Corpus too small for stable BERTopic (%s texts). Model will still initialize.",
                len(corpus),
            )
            corpus = corpus + ["placeholder journal entry about family and work"] * 5
        logger.info("Training BERTopic on %s documents", len(corpus))
        topic_model = BERTopic(
            embedding_model=self._embedding_model,
            umap_model=self._umap_model,
            hdbscan_model=self._hdbscan_model,
            language="english",
            calculate_probabilities=True,
            verbose=False,
        )
        topic_model.fit_transform(corpus)
        self._topic_model = topic_model
        out_dir = self._model_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            topic_model.save(str(out_dir), serialization="safetensors", save_ctfidf=True)
        except TypeError:
            topic_model.save(str(out_dir))
        logger.info("Saved topic model to %s", out_dir)

    def load(self) -> None:
        """Load a previously trained BERTopic model from disk."""
        path = self._model_dir()
        if not path.exists():
            raise FileNotFoundError(f"Missing topic model directory: {path}")
        self._topic_model = BERTopic.load(str(path))
        logger.info("Loaded topic model from %s", path)

    def _ensure_model(self) -> BERTopic:
        if self._topic_model is None:
            try:
                self.load()
            except FileNotFoundError:
                logger.warning("Topic model not found — training a lightweight default model.")
                self.train(
                    [
                        "I talked with my family about stress at work.",
                        "Doctor visit about sleep and anxiety.",
                        "Feeling lonely after the party with friends.",
                        "Reflecting on goals and self worth in my journal.",
                    ]
                )
        assert self._topic_model is not None
        return self._topic_model

    def assign_topic(self, text: str) -> str:
        """
        Assign a journal entry to the closest clinical domain.

        Args:
            text: Journal entry text.

        Returns:
            One of the six ``topic_domains`` labels from configuration.
        """
        model = self._ensure_model()
        transformed = model.transform([text])
        if isinstance(transformed, tuple):
            topics, _probs = transformed
        else:
            topics = transformed
        topic_id = int(topics[0]) if len(topics) else -1
        keywords: List[str] = []
        try:
            info = model.get_topic(topic_id)
            if info:
                keywords = [w for w, _ in info[:12]]
        except Exception:
            keywords = []
        if topic_id == -1 or not keywords:
            return self._zero_shot_domain(text)
        domain = self.map_to_domain(keywords)
        return domain if domain in self._domains else self._zero_shot_domain(text)

    def _zero_shot_domain(self, text: str) -> str:
        tokens = set(re.findall(r"[a-z]+", text.lower()))
        best = "self"
        best_hits = -1
        for dom, seeds in self._domain_seeds.items():
            hits = sum(1 for s in seeds if s in text.lower() or s in tokens)
            if hits > best_hits:
                best_hits = hits
                best = dom
        return best if best in self._domains else self._domains[0]

    def get_weekly_topic_matrix(self, weekly_windows: Dict[str, List[Dict[str, Any]]]) -> pd.DataFrame:
        """
        Build week-by-domain frequency matrix.

        Args:
            weekly_windows: Weekly buckets from the preprocessor.

        Returns:
            DataFrame with normalized domain counts per week.
        """
        rows: List[Dict[str, Any]] = []
        for week_id in sorted(weekly_windows.keys()):
            counts = {d: 0.0 for d in self._domains}
            entries = weekly_windows[week_id]
            n = max(len(entries), 1)
            for ent in entries:
                dom = self.assign_topic(str(ent.get("text", "")))
                if dom in counts:
                    counts[dom] += 1.0
            total = sum(counts.values()) or 1.0
            row = {d: counts[d] / total for d in self._domains}
            row["week_id"] = week_id
            rows.append(row)
        if not rows:
            return pd.DataFrame(columns=["week_id"] + self._domains)
        df = pd.DataFrame(rows).set_index("week_id")
        return df

    def map_to_domain(self, bertopic_keywords: Iterable[str]) -> str:
        """
        Map raw BERTopic keywords to a clinical domain label.

        Args:
            bertopic_keywords: Iterable of representative keywords.

        Returns:
            Domain string present in configuration.
        """
        words = [str(w).lower() for w in bertopic_keywords]
        scores = {d: 0.0 for d in self._domains}
        for dom, seeds in self._domain_seeds.items():
            for w in words:
                if w in seeds:
                    scores[dom] += 2.0
                for s in seeds:
                    if s in w or w in s:
                        scores[dom] += 1.0
        dom = max(scores, key=scores.get)
        if scores[dom] <= 0:
            return "self"
        return dom
