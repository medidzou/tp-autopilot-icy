"""Detector for ICy 3A courses based on syllabus keywords and Notion repository."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.syllabus.models import MatiereInfo

DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "mccc_icy.json"


def _normalize_text(text: str) -> str:
    """Lowercases and strips accents from text for resilient keyword matching."""
    text = text.lower()
    # Normalize unicode to decomposed form and remove combining accent marks
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


class CourseNotFoundError(KeyError):
    """Raised when a course ID cannot be found in the syllabus registry."""
    pass


class SyllabusDetector:
    """Detects ICy 3A academic course modules and maps them to syllabus resources."""

    def __init__(self, data_path: Optional[Path | str] = None) -> None:
        self.data_path = Path(data_path) if data_path else DEFAULT_DATA_PATH
        self._matieres: Dict[str, MatiereInfo] = {}
        self._load_data()

    def _load_data(self) -> None:
        """Loads course syllabus data from JSON."""
        if not self.data_path.exists():
            raise FileNotFoundError(f"Syllabus data file not found: {self.data_path}")

        with open(self.data_path, "r", encoding="utf-8") as f:
            raw_list = json.load(f)

        for item in raw_list:
            info = MatiereInfo(**item)
            self._matieres[info.id] = info

    def list_matieres(self) -> List[MatiereInfo]:
        """Returns all configured syllabus courses."""
        return list(self._matieres.values())

    def get_matiere(self, matiere_id: str) -> MatiereInfo:
        """Retrieves course information by ID.

        Raises:
            CourseNotFoundError: If matiere_id is not found in the syllabus.
        """
        if matiere_id not in self._matieres:
            raise CourseNotFoundError(f"Unknown matiere_id: '{matiere_id}'")
        return self._matieres[matiere_id]

    def get_notebook_url(self, matiere_id: str) -> str:
        """Retrieves Notion NotebookLM URL for a given course ID.

        Raises:
            CourseNotFoundError: If matiere_id is not found in the syllabus.
        """
        return self.get_matiere(matiere_id).notebook_url

    def detect_matiere(self, subject_text: str) -> MatiereInfo:
        """Detects the most relevant ICy 3A course for a given TP subject text.

        Raises:
            ValueError: If no relevant course keywords match the input text.
        """
        if not subject_text or not subject_text.strip():
            raise ValueError("Subject text cannot be empty.")

        norm_input = _normalize_text(subject_text)

        best_matiere: Optional[MatiereInfo] = None
        best_score = 0.0

        for matiere in self._matieres.values():
            score = 0.0

            # 1. Exact or partial match of course name / alias
            norm_nom = _normalize_text(matiere.nom)
            if norm_nom in norm_input:
                score += 40.0

            if matiere.alias:
                norm_alias = _normalize_text(matiere.alias)
                if norm_alias in norm_input:
                    score += 35.0

            # 2. Keyword scoring
            for kw in matiere.keywords:
                norm_kw = _normalize_text(kw)
                # Multi-word keyword search
                if " " in norm_kw or "-" in norm_kw or "_" in norm_kw or "(" in norm_kw:
                    if norm_kw in norm_input:
                        word_count = len(norm_kw.split())
                        score += 10.0 * max(1, word_count)
                else:
                    # Single word with regex boundary
                    pattern = rf"\b{re.escape(norm_kw)}\b"
                    matches = len(re.findall(pattern, norm_input))
                    if matches > 0:
                        score += 4.0 * min(matches, 3)

            # 3. Disambiguation heuristic: Langage C vs Programmation Système
            # If the text has system-specific syscalls (fork, pipe, pthread), penalize pure C
            if matiere.id == "langage_c":
                system_terms = ["fork", "pipe", "pthread", "mutex", "semaphore", "tube", "sigaction", "shm"]
                for term in system_terms:
                    if re.search(rf"\b{term}\b", norm_input):
                        score -= 8.0

            if score > best_score:
                best_score = score
                best_matiere = matiere

        if best_matiere is None or best_score <= 2.0:
            raise ValueError(
                f"Could not identify ICy 3A course for subject: '{subject_text[:120]}...'"
            )

        return best_matiere
