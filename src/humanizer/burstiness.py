"""Burstiness and statistical cadence scoring for human-like technical writing."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional
from src.profiles.models import StudentProfile


class BurstinessScorer:
    """Evaluates text burstiness (sentence length variance), lexical diversity (TTR),

    and robotic cadence indicators to ensure student report realism.
    """

    KNOWN_ABBREVIATIONS = (
        "ex.", "e.g.", "i.e.", "etc.", "cf.", "fig.", "tab.", "al.", "vs.",
        "dr.", "prof.", "str.",
    )

    def __init__(self, min_sentence_words: int = 1) -> None:
        self.min_sentence_words = min_sentence_words

    def split_sentences(self, text: str) -> List[str]:
        """Splits technical prose into sentences, avoiding false splits on abbreviations,

        decimal numbers, and source code filenames/struct accesses.
        """
        if not text or not text.strip():
            return []

        cleaned = text.strip()

        # Step 1: Protect known abbreviations with word boundary enforcement (\b)
        # Prevents false positive matching on words ending in '-al.' (optimal., terminal., etc.)
        abbr_map: Dict[str, str] = {}
        for idx, abbr in enumerate(self.KNOWN_ABBREVIATIONS):
            token = f"__ABBR_PROTECTED_{idx}__"
            pattern = re.compile(rf"\b{re.escape(abbr)}", re.IGNORECASE)
            if pattern.search(cleaned):
                abbr_map[token] = abbr
                cleaned = pattern.sub(token, cleaned)

        # Step 2: Protect decimal numbers (e.g., 3.14, 0.05)
        decimal_map: Dict[str, str] = {}
        def _preserve_decimal(match: re.Match[str]) -> str:
            token = f"__DEC_PROTECTED_{len(decimal_map)}__"
            decimal_map[token] = match.group(0)
            return token

        cleaned = re.sub(r"\b\d+\.\d+\b", _preserve_decimal, cleaned)

        # Step 3: Protect file names and struct member accesses (e.g., main.c, node.next)
        code_map: Dict[str, str] = {}
        def _preserve_code_dot(match: re.Match[str]) -> str:
            token = f"__CODE_PROTECTED_{len(code_map)}__"
            code_map[token] = match.group(0)
            return token

        cleaned = re.sub(r"\b[a-zA-Z_]\w*\.[a-zA-Z_]\w*\b", _preserve_code_dot, cleaned)

        # Step 4: Split sentences on sentence-ending punctuation followed by whitespace or end of line
        raw_parts = re.split(r"(?<=[.!?])\s+|\n+", cleaned)

        # Step 5: Restore placeholders and clean whitespace
        sentences: List[str] = []
        for part in raw_parts:
            s = part.strip()
            if not s:
                continue

            for token, orig in code_map.items():
                s = s.replace(token, orig)
            for token, orig in decimal_map.items():
                s = s.replace(token, orig)
            for token, orig in abbr_map.items():
                s = s.replace(token, orig)

            if len(self.tokenize_words(s)) >= self.min_sentence_words:
                sentences.append(s)

        return sentences

    def tokenize_words(self, text: str) -> List[str]:
        """Extracts individual word tokens, supporting French contractions and hyphenated terms."""
        return re.findall(r"\b[\w'-]+\b", text)

    def calculate_sentence_variance(self, text: str) -> float:
        """Calculates population variance of sentence lengths (word count per sentence).

        High variance (burstiness) is characteristic of human writing; flat variance suggests AI.
        """
        sentences = self.split_sentences(text)
        if len(sentences) < 2:
            return 0.0

        lengths = [len(self.tokenize_words(s)) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((x - mean_len) ** 2 for x in lengths) / len(lengths)
        return round(float(variance), 4)

    def calculate_sentence_std_dev(self, text: str) -> float:
        """Calculates standard deviation of sentence lengths."""
        return round(math.sqrt(self.calculate_sentence_variance(text)), 4)

    def calculate_ttr(self, text: str) -> float:
        """Calculates Type-Token Ratio (unique lowercased words / total words)."""
        words = self.tokenize_words(text)
        if not words:
            return 0.0
        unique_words = {w.lower() for w in words}
        return round(len(unique_words) / len(words), 4)

    def calculate_metrics(self, text: str) -> Dict[str, Any]:
        """Computes comprehensive statistical cadence metrics for the given text."""
        sentences = self.split_sentences(text)
        words = self.tokenize_words(text)
        sentence_count = len(sentences)
        word_count = len(words)

        if sentence_count == 0 or word_count == 0:
            return {
                "sentence_count": 0,
                "word_count": 0,
                "mean_sentence_length": 0.0,
                "sentence_variance": 0.0,
                "sentence_std_dev": 0.0,
                "ttr": 0.0,
                "burstiness_score": 0.0,
                "is_robotic": False,
            }

        lengths = [len(self.tokenize_words(s)) for s in sentences]
        mean_length = round(sum(lengths) / sentence_count, 2)
        variance = self.calculate_sentence_variance(text)
        std_dev = round(math.sqrt(variance), 2)
        ttr = self.calculate_ttr(text)
        score = self.calculate_score(text)
        is_robotic = self.is_robotic_cadence(text)

        return {
            "sentence_count": sentence_count,
            "word_count": word_count,
            "mean_sentence_length": mean_length,
            "sentence_variance": variance,
            "sentence_std_dev": std_dev,
            "ttr": ttr,
            "burstiness_score": score,
            "is_robotic": is_robotic,
        }

    def calculate_score(self, text: str, profile: Optional[StudentProfile] = None) -> float:
        """Computes an overall burstiness & naturalness score (0.0 to 1.0).

        Higher scores reflect high variation in sentence lengths and strong vocabulary richness.
        If a StudentProfile is provided, blends general naturalness with profile adherence.
        """
        sentences = self.split_sentences(text)
        words = self.tokenize_words(text)
        if not sentences or not words:
            return 0.0

        lengths = [len(self.tokenize_words(s)) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = self.calculate_sentence_variance(text)
        std_dev = math.sqrt(variance)

        cv = (std_dev / mean_len) if mean_len > 0 else 0.0
        ttr = self.calculate_ttr(text)

        # Coefficient of variation in natural human text is typically 0.40 - 0.85
        burstiness_factor = min(1.0, cv / 0.50)
        # TTR in technical reports typically ranges from 0.45 to 0.75
        lexical_factor = min(1.0, ttr / 0.60)

        # Single sentence penalty
        sentence_penalty = 0.5 if len(sentences) == 1 else 1.0

        base_score = (0.60 * burstiness_factor + 0.40 * lexical_factor) * sentence_penalty
        base_score = min(1.0, max(0.0, base_score))

        if profile is not None:
            profile_fit = self.evaluate_profile_fit(text, profile)
            final_score = 0.60 * base_score + 0.40 * profile_fit
            return round(final_score, 4)

        return round(base_score, 4)

    def is_robotic_cadence(self, text: str, min_variance: float = 3.0) -> bool:
        """Returns True if the text displays an unnaturally uniform, metronomic sentence rhythm."""
        sentences = self.split_sentences(text)
        if len(sentences) < 3:
            return False
        return self.calculate_sentence_variance(text) < min_variance

    def evaluate_profile_fit(self, text: str, profile: StudentProfile) -> float:
        """Compares text metrics against the student's calibrated stylistic profile (0.0 to 1.0)."""
        metrics = self.calculate_metrics(text)
        p_metrics = profile.verbosity_metrics or profile.refresh_metrics()

        target_len = float(p_metrics.get("avg_sentence_length", 12.0))
        target_ttr = float(p_metrics.get("lexical_diversity", 0.60))

        if target_len <= 0.0:
            target_len = 12.0
        if target_ttr <= 0.0:
            target_ttr = 0.60

        actual_len = metrics["mean_sentence_length"]
        actual_ttr = metrics["ttr"]

        len_diff_ratio = abs(actual_len - target_len) / target_len
        len_score = max(0.0, 1.0 - min(1.0, len_diff_ratio))

        ttr_diff_ratio = abs(actual_ttr - target_ttr) / target_ttr
        ttr_score = max(0.0, 1.0 - min(1.0, ttr_diff_ratio))

        fit = 0.50 * len_score + 0.50 * ttr_score
        return round(float(fit), 4)

    def suggest_cadence_fixes(self, text: str) -> List[str]:
        """Provides actionable feedback when text exhibits robotic or monotone cadence."""
        suggestions: List[str] = []
        metrics = self.calculate_metrics(text)

        if metrics["sentence_count"] >= 3 and metrics["sentence_variance"] < 3.0:
            suggestions.append(
                f"Cadence trop monotone (variance={metrics['sentence_variance']:.2f}). "
                "Alternez des phrases courtes et des explications techniques détaillées."
            )
        if metrics["mean_sentence_length"] > 25.0:
            suggestions.append(
                f"Phrases trop longues en moyenne ({metrics['mean_sentence_length']:.1f} mots). "
                "Scindez certaines phrases pour alléger la lecture."
            )
        if metrics["ttr"] < 0.40 and metrics["word_count"] > 30:
            suggestions.append(
                f"Vocabulaire répétitif (TTR={metrics['ttr']:.2f}). "
                "Enrichissez le vocabulaire technique et évitez les répétitions."
            )
        return suggestions
