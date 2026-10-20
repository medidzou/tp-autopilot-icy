"""Subject ingestion parser for TP documents (Markdown, plain text, and PDF)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _normalize_search_text(text: str) -> str:
    """Lowercases and strips accents from text for resilient keyword matching."""
    text = text.lower()
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass
class SubjectRequirement:
    """Represents an extracted requirement or constraint from a TP subject."""

    category: str  # 'constraint', 'objective', 'forbidden', 'deliverable', 'library'
    description: str
    mandatory: bool = True


@dataclass
class ParsedSubject:
    """Represents structured metadata and constraints extracted from a TP subject document."""

    title: str
    matiere_hint: Optional[str] = None
    objectives: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    forbidden_approaches: List[str] = field(default_factory=list)
    required_functions: List[str] = field(default_factory=list)
    deliverables: List[str] = field(default_factory=list)
    allowed_libraries: List[str] = field(default_factory=list)
    raw_text: str = ""
    requirements: List[SubjectRequirement] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        """Returns a summarized dictionary of the parsed subject."""
        return {
            "title": self.title,
            "matiere_hint": self.matiere_hint,
            "objectives_count": len(self.objectives),
            "constraints_count": len(self.constraints),
            "forbidden_count": len(self.forbidden_approaches),
            "required_functions_count": len(self.required_functions),
            "deliverables": self.deliverables,
        }


class SubjectParser:
    """Parses TP subject specifications from text, Markdown, or PDF documents."""

    # Keywords for detecting course topics
    COURSE_KEYWORDS: Dict[str, List[str]] = {
        "prog_systeme": [
            "programmation systeme", "systeme", "semaphore", "semaphores",
            "memoire partagee", "shm", "pthread", "mutex", "fork", "pipe", "tube",
            "ipc", "waitpid", "sigaction", "signal"
        ],
        "langage_c": [
            "langage c", "c niveau 2", "pointeur", "pointeurs", "malloc",
            "free", "c11"
        ],
        "java_poo": [
            "java", "poo", "classe", "classes", "interface", "scanner",
            "heritage", "polymorphisme", "encapsulation"
        ],
        "archi_avancee": [
            "architecture avancee", "assembleur", "nasm", "pipeline",
            "registre", "alu", "mips", "risc"
        ],
        "bdd": [
            "base de donnees", "bases de donnees", "sql", "relationnel",
            "cle primaire", "select", "jointure", "foreign key"
        ],
        "prog_lineaire": [
            "programmation lineaire", "simplexe", "optimisation",
            "contraintes", "fonction objectif"
        ],
        "complexite": [
            "complexite", "o(n", "np-complet", "turing", "reduction",
            "graphe", "dijkstra"
        ],
    }

    def parse_file(self, file_path: str | Path) -> ParsedSubject:
        """Parses a TP subject from a file path (.txt, .md, .pdf).

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If file format is not supported or content cannot be read.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Subject file not found: {file_path}")

        suffix = path.suffix.lower()

        if suffix in (".txt", ".md", ".rst"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="latin-1", errors="replace")
            return self.parse_text(text, default_title=path.stem)

        if suffix == ".pdf":
            text = self._extract_text_from_pdf(path)
            return self.parse_text(text, default_title=path.stem)

        raise ValueError(f"Unsupported subject file format: {suffix} (expected .md, .txt, .pdf)")

    def _extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extracts text content from a PDF file using available libraries."""
        # Try PyMuPDF (pymupdf) first to avoid deprecation warning
        try:
            try:
                import pymupdf as fitz  # type: ignore
            except ImportError:
                import fitz  # type: ignore

            doc = fitz.open(str(pdf_path))
            pages_text = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(pages_text).strip()
        except ImportError:
            pass

        # Try pdfplumber second
        try:
            import pdfplumber  # type: ignore

            pages_text = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page in pdf.pages:
                    txt = page.extract_text()
                    if txt:
                        pages_text.append(txt)
            return "\n\n".join(pages_text).strip()
        except ImportError:
            pass

        raise ImportError(
            "Neither PyMuPDF (fitz) nor pdfplumber is available to extract text from PDF."
        )

    def parse_text(self, text: str, default_title: Optional[str] = None) -> ParsedSubject:
        """Parses subject text and extracts constraints, forbidden approaches, and metadata."""
        if not text or not text.strip():
            return ParsedSubject(title=default_title or "Sujet Inconnu", raw_text="")

        clean_text = text.strip()
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]

        title = self._extract_title(lines, default_title)
        matiere_hint = self._detect_matiere_hint(clean_text)
        objectives = self._extract_objectives(lines)
        constraints = self._extract_constraints(lines)
        forbidden = self._extract_forbidden(lines)
        required_functions = self._extract_required_functions(clean_text)
        deliverables = self._extract_deliverables(lines)
        allowed_libs = self._extract_allowed_libraries(clean_text)

        # Aggregate requirements
        requirements: List[SubjectRequirement] = []
        for c in constraints:
            requirements.append(SubjectRequirement(category="constraint", description=c, mandatory=True))
        for f in forbidden:
            requirements.append(SubjectRequirement(category="forbidden", description=f, mandatory=True))
        for o in objectives:
            requirements.append(SubjectRequirement(category="objective", description=o, mandatory=False))
        for d in deliverables:
            requirements.append(SubjectRequirement(category="deliverable", description=d, mandatory=True))
        for l in allowed_libs:
            requirements.append(SubjectRequirement(category="library", description=l, mandatory=False))

        return ParsedSubject(
            title=title,
            matiere_hint=matiere_hint,
            objectives=objectives,
            constraints=constraints,
            forbidden_approaches=forbidden,
            required_functions=required_functions,
            deliverables=deliverables,
            allowed_libraries=allowed_libs,
            raw_text=clean_text,
            requirements=requirements,
        )

    def _extract_title(self, lines: List[str], default_title: Optional[str]) -> str:
        """Extracts title from Markdown header or first relevant line."""
        for line in lines:
            if line.startswith("#"):
                clean = re.sub(r"^#+\s*", "", line).strip()
                if clean:
                    return clean
            # Line matching "TP ..." or "Travaux Pratiques ..."
            if re.match(r"^(TP\s*\d+|Travaux\s+Pratiques|Projet)\b", line, re.IGNORECASE):
                return line.strip()

        return default_title or (lines[0] if lines else "Sujet Inconnu")

    def _detect_matiere_hint(self, text: str) -> Optional[str]:
        """Detects course ID hint based on keyword frequencies and disambiguation."""
        norm = _normalize_search_text(text)
        best_id: Optional[str] = None
        best_score = 0.0

        for m_id, kws in self.COURSE_KEYWORDS.items():
            score = 0.0
            for kw in kws:
                norm_kw = _normalize_search_text(kw)
                if norm_kw in norm:
                    # Longer keywords carry much higher weight
                    weight = 10.0 if " " in norm_kw else 3.0
                    score += weight

            # Disambiguation heuristic: if system terms are found, reduce pure C score
            if m_id == "langage_c":
                for sys_term in ("semaphore", "pthread", "shm", "fork", "pipe", "systeme"):
                    if sys_term in norm:
                        score -= 6.0

            if score > best_score and score >= 2.0:
                best_score = score
                best_id = m_id

        return best_id

    def _extract_objectives(self, lines: List[str]) -> List[str]:
        """Extracts stated pedagogical objectives from the subject text."""
        objectives: List[str] = []
        in_obj_section = False

        for line in lines:
            norm = _normalize_search_text(line)
            if any(h in norm for h in ("objectif", "but du tp", "introduction")):
                in_obj_section = True
                continue
            if in_obj_section:
                # End section on next header or empty line or constraint header
                if line.startswith("#") or any(h in norm for h in ("consigne", "contrainte", "rendu", "exercice")):
                    in_obj_section = False
                    continue
                clean = re.sub(r"^[-*•0-9.)]\s*", "", line).strip()
                if clean and len(clean) > 8:
                    objectives.append(clean)

        return objectives

    def _extract_constraints(self, lines: List[str]) -> List[str]:
        """Extracts hard technical constraints (e.g. gcc -Wall -Werror, sans récursion, etc.)."""
        constraints: List[str] = []
        pattern = re.compile(
            r"\b(obligatoire|impératif|doit|doivent|exigé|sanctionné|warning|sans warning|-Wall|-Werror|valgrind)\b",
            re.IGNORECASE,
        )

        for line in lines:
            if pattern.search(line):
                clean = re.sub(r"^[-*•0-9.)]\s*", "", line).strip()
                if clean and clean not in constraints:
                    constraints.append(clean)

        return constraints

    def _extract_forbidden(self, lines: List[str]) -> List[str]:
        """Extracts strictly forbidden approaches and constructs."""
        forbidden: List[str] = []
        pattern = re.compile(
            r"\b(interdit|interdite|interdits|proscrit|défendu|ne pas utiliser|sans récurs|aucune variable globale)\b",
            re.IGNORECASE,
        )

        for line in lines:
            if pattern.search(line):
                clean = re.sub(r"^[-*•0-9.)]\s*", "", line).strip()
                if clean and clean not in forbidden:
                    forbidden.append(clean)

        return forbidden

    def _extract_required_functions(self, text: str) -> List[str]:
        """Extracts function names identified in the subject instructions."""
        found: Set[str] = set()

        # Pattern 1: C-style signatures in backticks or text: `int compute_checksum(...)`
        matches = re.findall(
            r"`?\b(?:int|void|char|double|float|size_t|bool|unsigned)\s*\*?\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
            text,
        )
        for m in matches:
            if m not in ("if", "while", "for", "switch", "sizeof", "main"):
                found.add(m)

        # Pattern 2: Explicit "fonction `name`" or "fonction `name(...)`"
        explicit = re.findall(r"fonction\s+[`\"']?([a-zA-Z_][a-zA-Z0-9_]*)[`\"']?", text, re.IGNORECASE)
        for m in explicit:
            if m not in ("if", "while", "for", "main"):
                found.add(m)

        return sorted(list(found))

    def _extract_deliverables(self, lines: List[str]) -> List[str]:
        """Extracts expected deliverables and file extensions from submission instructions."""
        deliverables: List[str] = []
        pattern = re.compile(
            r"\b(rendre|déposer|livrable|rendu|archive|\.tar\.gz|\.zip|makefile|rapport)\b",
            re.IGNORECASE,
        )

        for line in lines:
            if pattern.search(line):
                clean = re.sub(r"^[-*•0-9.)]\s*", "", line).strip()
                if clean and clean not in deliverables:
                    deliverables.append(clean)

        return deliverables

    def _extract_allowed_libraries(self, text: str) -> List[str]:
        """Extracts explicitly mentioned header files or packages."""
        found: Set[str] = set()
        c_includes = re.findall(r"<([a-zA-Z0-9_\-\.\/]+\.h)>", text)
        for inc in c_includes:
            found.add(f"<{inc}>")

        java_imports = re.findall(r"\bimport\s+([a-zA-Z0-9_\.]+);", text)
        for imp in java_imports:
            found.add(imp)

        return sorted(list(found))
