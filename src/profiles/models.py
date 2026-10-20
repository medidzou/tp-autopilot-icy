"""Data models for student profiles and calibration questionnaire."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

DEFAULT_CALIBRATION_QUESTIONS: Dict[str, str] = {
    "explication_concept": "Comment expliques-tu un concept technique avec tes propres mots ? (ex: pointeurs, polymorphisme)",
    "style_code": "Quelles sont tes habitudes d'écriture de code ? (nommage snake_case/camelCase, boucles while/for, découpage modulaire)",
    "gestion_erreurs": "Comment gères-tu les vérifications d'erreur et cas limites ? (assert, retours d'erreur conditionnels, errno)",
}


def compute_text_verbosity_metrics(
    samples: List[str], calibration_answers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Computes basic text verbosity and stylistic metrics from writing samples and calibration answers."""
    all_texts: List[str] = list(samples)
    if calibration_answers:
        all_texts.extend(str(v) for v in calibration_answers.values() if v)

    full_text = " ".join(all_texts).strip()
    if not full_text:
        return {
            "sample_count": len(samples),
            "total_words": 0,
            "total_sentences": 0,
            "avg_sentence_length": 0.0,
            "vocabulary_size": 0,
            "lexical_diversity": 0.0,
        }

    # Extract sentences and words
    raw_sentences = [s.strip() for s in re.split(r"[.!?]+", full_text) if s.strip()]
    words = re.findall(r"\b\w+\b", full_text)
    total_words = len(words)
    total_sentences = len(raw_sentences) if raw_sentences else 1
    unique_words = len({w.lower() for w in words})

    avg_sentence_length = round(total_words / max(1, total_sentences), 2)
    lexical_diversity = round(unique_words / total_words, 3) if total_words > 0 else 0.0

    return {
        "sample_count": len(samples),
        "total_words": total_words,
        "total_sentences": total_sentences,
        "avg_sentence_length": avg_sentence_length,
        "vocabulary_size": unique_words,
        "lexical_diversity": lexical_diversity,
    }


class StudentProfile(BaseModel):
    """Represents a student's technical writing profile, stylistic markers, and calibration data."""

    name: str
    calibration_answers: Dict[str, str] = Field(default_factory=dict)
    samples: List[str] = Field(default_factory=list)
    verbosity_metrics: Dict[str, Any] = Field(default_factory=dict)
    style_preferences: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def refresh_metrics(self) -> Dict[str, Any]:
        """Recalculates verbosity metrics based on current samples and calibration answers."""
        metrics = compute_text_verbosity_metrics(
            samples=self.samples,
            calibration_answers=self.calibration_answers,
        )
        self.verbosity_metrics = metrics
        return metrics
