"""
Text preprocessing for LAPA journal entries.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import spacy
from transformers import AutoTokenizer

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """
    Cleans journal text, tokenizes with RoBERTa, segments entries by week,
    and produces exploratory summaries.
    """

    _NEG_PATTERN = re.compile(
        r"\b(not|no|never|nothing|nowhere|nobody|neither|nor|n't)\b",
        re.IGNORECASE,
    )
    _URL_PATTERN = re.compile(
        r"https?://\S+|www\.\S+",
        re.IGNORECASE,
    )
    _NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
    _SPECIAL_PATTERN = re.compile(r"[^a-z0-9\s']", re.IGNORECASE)

    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize SpaCy and RoBERTa tokenizer from configuration.

        Args:
            config: Loaded YAML configuration dictionary.
        """
        self._config = config
        self._max_len = int(config.get("max_seq_length", 512))
        model_name = config.get("roberta_model", "roberta-base")
        self._tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
        self._nlp: Optional[spacy.language.Language] = None

    def _get_nlp(self) -> spacy.language.Language:
        """Lazily load SpaCy to keep import/start time reasonable."""
        if self._nlp is None:
            try:
                self._nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
            except OSError as exc:
                logger.error(
                    "SpaCy model en_core_web_sm is missing. "
                    "Install with: python -m spacy download en_core_web_sm"
                )
                raise exc
        return self._nlp

    def clean_text(self, text: str) -> str:
        """
        Lowercase, strip URLs/numbers, remove most punctuation, lemmatize.

        Preserves common negation cues and keeps sentiment-bearing stopwords
        by avoiding aggressive stopword removal.

        Args:
            text: Raw journal entry.

        Returns:
            Normalized string suitable for classical/NLP features.
        """
        if not text or not str(text).strip():
            return ""
        raw = str(text).strip()
        lowered = raw.lower()
        neg_spans = list(self._NEG_PATTERN.finditer(lowered))
        neg_tokens = {m.group(0).lower() for m in neg_spans}
        no_url = self._URL_PATTERN.sub(" ", lowered)
        no_num = self._NUMBER_PATTERN.sub(" ", no_url)
        no_special = self._SPECIAL_PATTERN.sub(" ", no_num)
        collapsed = re.sub(r"\s+", " ", no_special).strip()
        if not collapsed:
            return ""
        nlp = self._get_nlp()
        doc = nlp(collapsed)
        lemmas: List[str] = []
        for token in doc:
            if token.is_space or token.is_punct:
                continue
            lemma = token.lemma_.lower().strip()
            if not lemma:
                continue
            lemmas.append(lemma)
        out = " ".join(lemmas)
        for tok in neg_tokens:
            if tok not in out.split():
                out = f"{tok} {out}".strip()
        return out

    def tokenize(self, text: str) -> Dict[str, Any]:
        """
        Tokenize with the configured RoBERTa tokenizer.

        Args:
            text: Raw or cleaned text (raw is typical for transformers).

        Returns:
            Dictionary with input_ids and attention_mask tensors/lists.
        """
        enc = self._tokenizer(
            text,
            truncation=True,
            padding="max_length",
            max_length=self._max_len,
            return_tensors="pt",
        )
        return {
            "input_ids": enc["input_ids"],
            "attention_mask": enc["attention_mask"],
        }

    def segment_to_weekly_windows(self, entries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group entries by ISO calendar week.

        Each entry should contain ``text`` and ``date`` (ISO ``YYYY-MM-DD``).

        Args:
            entries: Chronological or arbitrary journal records.

        Returns:
            Mapping ``week_id`` -> list of entries for that week.
        """
        buckets: Dict[str, List[Dict[str, Any]]] = {}
        for item in entries or []:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            date_str = item.get("date", "")
            week_id = self._week_key(date_str)
            if not week_id:
                continue
            buckets.setdefault(week_id, []).append(
                {
                    "text": text,
                    "date": date_str,
                    "meta": item.get("meta", {}),
                }
            )
        for wid, lst in buckets.items():
            n = max(len(lst), 1)
            for row in lst:
                row["week_norm"] = 1.0 / float(n)
        return buckets

    def run_eda(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Lightweight exploratory summaries for monitoring data quality.

        Args:
            entries: Same structure as :meth:`segment_to_weekly_windows`.

        Returns:
            Summary dictionary with counts and simple lexical stats.
        """
        if not entries:
            return {
                "entry_count_per_week": {},
                "average_entry_length": 0.0,
                "vocabulary_size": 0,
                "writing_frequency_score": 0.0,
            }
        weeks = self.segment_to_weekly_windows(entries)
        per_week = {k: len(v) for k, v in weeks.items()}
        lengths = [len(str(e.get("text", ""))) for e in entries if e.get("text")]
        avg_len = float(sum(lengths) / max(len(lengths), 1))
        cleaned_tokens: List[str] = []
        for e in entries:
            ct = self.clean_text(str(e.get("text", "")))
            cleaned_tokens.extend(ct.split())
        vocab = set(cleaned_tokens)
        num_weeks = max(len(per_week), 1)
        freq_score = float(len(entries)) / float(num_weeks)
        return {
            "entry_count_per_week": per_week,
            "average_entry_length": avg_len,
            "vocabulary_size": len(vocab),
            "writing_frequency_score": freq_score,
        }

    @staticmethod
    def _week_key(date_str: str) -> str:
        """Return ISO year-week identifier."""
        if not date_str:
            return ""
        try:
            dt = datetime.fromisoformat(str(date_str)[:10])
        except ValueError:
            return ""
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
