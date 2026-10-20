"""AST and token n-gram similarity checker simulating academic plagiarism detectors (MOSS, JPlag).

Implements structure-preserving lexical normalization, token n-grams, winnowing
fingerprints, pairwise similarity matrices, and anti-plagiarism threshold verification.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple


class PairwiseSimilarityMatrix(dict):
    """Bidirectional pairwise similarity dictionary.

    Allows lookup with both `matrix[(a, b)]` and `matrix[(b, a)]` while storing
    canonical pairs `(min(a, b), max(a, b))`.
    """

    def __contains__(self, key: object) -> bool:
        if super().__contains__(key):
            return True
        if isinstance(key, tuple) and len(key) == 2:
            reversed_key = (key[1], key[0])
            return super().__contains__(reversed_key)
        return False

    def __getitem__(self, key: Tuple[str, str]) -> float:
        if super().__contains__(key):
            return super().__getitem__(key)
        if isinstance(key, tuple) and len(key) == 2:
            reversed_key = (key[1], key[0])
            if super().__contains__(reversed_key):
                return super().__getitem__(reversed_key)
        raise KeyError(key)

    def get(self, key: Tuple[str, str], default: Optional[float] = None) -> Optional[float]:
        try:
            return self[key]
        except KeyError:
            return default


class SimilarityChecker:
    """Computes AST / structural token similarities between source code files.

    Simulates MOSS (Stanford) and JPlag (Karlsruhe) plagiarism detectors:
    1. Lexical normalization: comments and whitespace stripped, literals normalized.
    2. Structural abstraction: identifiers mapped to ID, types to TYPE:<type>, keywords preserved.
    3. Token n-gram overlap: multiset Dice coefficient on structural n-grams.
    4. Optional winnowing fingerprints for document-scale indexing.
    """

    KEYWORDS: Set[str] = {
        "for", "while", "do", "if", "else", "switch", "case", "default",
        "break", "continue", "return", "goto", "sizeof", "struct", "typedef",
        "union", "enum", "class", "public", "private", "protected", "static",
        "const", "inline", "extern", "volatile", "try", "catch", "throw",
        "new", "this", "super", "interface", "extends", "implements", "final",
        "import", "package", "virtual", "override", "template", "namespace",
    }

    TYPES: Set[str] = {
        "int", "char", "float", "double", "void", "long", "short", "unsigned",
        "signed", "size_t", "ssize_t", "bool", "boolean", "uint8_t", "uint16_t",
        "uint32_t", "uint64_t", "int8_t", "int16_t", "int32_t", "int64_t",
        "intptr_t", "uintptr_t", "String", "auto", "byte",
    }

    def __init__(self, default_ngram_size: int = 6) -> None:
        self.default_ngram_size = default_ngram_size

    def tokenize(self, code: str) -> List[str]:
        """Normalizes and tokenizes C / Java source code into structural tokens."""
        if not code or not code.strip():
            return []

        # 1. Strip line and block comments
        cleaned = re.sub(r"//.*", "", code)
        cleaned = re.sub(r"/\*[\s\S]*?\*/", "", cleaned)

        # 2. Strip preprocessor directives (#include, #define, etc.)
        cleaned = re.sub(r"^\s*#.*$", "", cleaned, flags=re.MULTILINE)

        # 3. Normalize string and character literals

        cleaned = re.sub(r'"(\\.|[^"\\])*"', " STR_LIT ", cleaned)
        cleaned = re.sub(r"'(\\.|[^'\\])*'", " CHAR_LIT ", cleaned)

        # 3. Extract tokens
        # Multi-char operators, single-char delimiters, numbers, and identifiers
        tok_regex = (
            r"(->|::|\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|<<=|>>=|==|!=|<=|>=|"
            r"&&|\|\||<<|>>|[{}()\[\],;+*&|<>\-=/!%~?:^]|"
            r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b|\b[a-zA-Z_]\w*\b)"
        )
        raw_tokens = re.findall(tok_regex, cleaned)

        normalized: List[str] = []
        for t in raw_tokens:
            if t in self.KEYWORDS:
                normalized.append(t)
            elif t in self.TYPES:
                normalized.append(f"TYPE:{t}")
            elif re.match(r"^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$", t):
                normalized.append("NUM")
            elif t in {"STR_LIT", "CHAR_LIT"}:
                normalized.append(t)
            elif re.match(r"^[a-zA-Z_]\w*$", t):
                normalized.append("ID")
            else:
                normalized.append(t)

        return normalized

    def extract_ngrams(self, tokens: List[str], n: int = 4) -> List[Tuple[str, ...]]:
        """Extracts n-grams from a normalized token stream."""
        if not tokens:
            return []
        if len(tokens) <= n:
            return [tuple(tokens)]
        return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]

    def calculate_ast_similarity(
        self,
        code_a: str,
        code_b: str,
        n: Optional[int] = None,
        base_code: Optional[Union[str, Sequence[str]]] = None,
    ) -> float:
        """Computes structural AST / token similarity between two source code snippets.

        Returns a score in [0.0, 1.0].
        - Identical code (or code differing only by comments / whitespace / variable names): 1.0
        - Completely disjoint code: 0.0
        - If base_code is provided (e.g. skeleton / template code), n-grams from base_code
          are excluded, simulating MOSS's -b flag.
        """
        tok_a = self.tokenize(code_a)
        tok_b = self.tokenize(code_b)

        if not tok_a and not tok_b:
            return 1.0
        if not tok_a or not tok_b:
            return 0.0

        n_size = n if n is not None else self.default_ngram_size

        # If token sequences are shorter than n_size, adapt n
        effective_n = min(n_size, len(tok_a), len(tok_b))
        if effective_n < 1:
            effective_n = 1

        base_ngrams: Set[Tuple[str, ...]] = set()
        if base_code:
            base_list = [base_code] if isinstance(base_code, str) else list(base_code)
            for b in base_list:
                cleaned_b = re.sub(r"^\s*#.*", "", b, flags=re.MULTILINE)
                tok_b_base = self.tokenize(cleaned_b)
                for ng in self.extract_ngrams(tok_b_base, effective_n):
                    base_ngrams.add(ng)
                # Also include prototype header variants ending with { instead of ;
                alt_b = re.sub(r"\)\s*;", ") {", cleaned_b)
                if alt_b != cleaned_b:
                    tok_alt = self.tokenize(alt_b)
                    for ng in self.extract_ngrams(tok_alt, effective_n):
                        base_ngrams.add(ng)

        ng1_list = self.extract_ngrams(tok_a, effective_n)
        ng2_list = self.extract_ngrams(tok_b, effective_n)

        if base_ngrams:
            ng1_list = [ng for ng in ng1_list if ng not in base_ngrams]
            ng2_list = [ng for ng in ng2_list if ng not in base_ngrams]

        if not ng1_list and not ng2_list:
            return 1.0
        if not ng1_list or not ng2_list:
            return 0.0

        ng1 = Counter(ng1_list)
        ng2 = Counter(ng2_list)

        intersection_count = sum((ng1 & ng2).values())
        total_count = (sum(ng1.values()) + sum(ng2.values())) / 2.0

        if total_count <= 0:
            return 0.0

        similarity = intersection_count / total_count
        return round(min(1.0, max(0.0, similarity)), 4)

    def winnow(
        self, tokens: List[str], k: int = 4, w: int = 4
    ) -> Set[int]:
        """Implements the Stanford Winnowing algorithm for document fingerprinting.

        - k: token k-gram length
        - w: window size in hashes
        Returns a set of selected fingerprint hashes.
        """
        ngrams = self.extract_ngrams(tokens, k)
        if not ngrams:
            return set()

        # Hash each k-gram to a 32-bit integer
        hashes = [
            int(hashlib.md5(" ".join(ng).encode("utf-8")).hexdigest()[:8], 16)
            for ng in ngrams
        ]

        if len(hashes) <= w:
            return {min(hashes)}

        fingerprints: Set[int] = set()
        for i in range(len(hashes) - w + 1):
            window = hashes[i : i + w]
            min_val = min(window)
            fingerprints.add(min_val)

        return fingerprints

    def calculate_winnowing_similarity(
        self, code_a: str, code_b: str, k: int = 4, w: int = 4
    ) -> float:
        """Calculates Jaccard similarity of Winnowing fingerprints."""
        tok_a = self.tokenize(code_a)
        tok_b = self.tokenize(code_b)

        if not tok_a and not tok_b:
            return 1.0
        if not tok_a or not tok_b:
            return 0.0

        fp_a = self.winnow(tok_a, k=k, w=w)
        fp_b = self.winnow(tok_b, k=k, w=w)

        if not fp_a and not fp_b:
            return 1.0
        if not fp_a or not fp_b:
            return 0.0

        intersection = len(fp_a & fp_b)
        union = len(fp_a | fp_b)

        return round(intersection / union, 4) if union > 0 else 0.0

    def compute_pairwise_similarity(
        self,
        solutions: Dict[str, str],
        n: Optional[int] = None,
        base_code: Optional[Union[str, Sequence[str]]] = None,
    ) -> PairwiseSimilarityMatrix:
        """Calculates pairwise similarity for all student solution pairs."""
        matrix = PairwiseSimilarityMatrix()
        student_keys = sorted(solutions.keys())

        for a, b in combinations(student_keys, 2):
            sim = self.calculate_ast_similarity(
                solutions[a], solutions[b], n=n, base_code=base_code
            )
            matrix[(a, b)] = sim

        return matrix

    def verify_threshold(
        self,
        solutions: Dict[str, str],
        max_threshold: float = 0.12,
        base_code: Optional[Union[str, Sequence[str]]] = None,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """Verifies that all student solution pairs respect the anti-MOSS threshold.

        Returns:
            (is_compliant: bool, flagged_pairs: List[Dict[str, Any]])
        """
        matrix = self.compute_pairwise_similarity(solutions, base_code=base_code)
        flagged: List[Dict[str, Any]] = []

        for (a, b), score in matrix.items():
            if score > max_threshold:
                flagged.append(
                    {
                        "student_a": a,
                        "student_b": b,
                        "similarity": score,
                        "threshold": max_threshold,
                        "status": "FLAGGED",
                    }
                )

        return len(flagged) == 0, flagged



AntiMossSimilarityChecker = SimilarityChecker
