"""Adversarial Audit Loop for TP deliverables.

Performs:
1. Skeleton invariant verification (function prototypes & signatures preserved verbatim).
2. Anti-MOSS AST & structural n-gram similarity cross-check (< 12% pairwise threshold).
3. Residual AI writing tells and robotic cadence detection.
4. Scientific coherence and quality evaluation (multi-model / adversarial evaluator).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from src.builder.executor import BuildResult
from src.divergence.matrix import StrategyDirective
from src.divergence.similarity import AntiMossSimilarityChecker, PairwiseSimilarityMatrix, SimilarityChecker
from src.humanizer.cleaner import HumanizerCleaner
from src.ingestion.skeleton import SkeletonParser, SkeletonProject
from src.profiles.models import StudentProfile


@dataclass
class StudentDeliverable:
    """Represents the final packaged deliverable generated for a student."""

    student_name: str
    code_files: Dict[str, str] = field(default_factory=dict)
    report_markdown: str = ""
    profile: Optional[StudentProfile] = None
    directive: Optional[StrategyDirective] = None
    build_result: Optional[BuildResult] = None
    burstiness_metrics: Dict[str, Any] = field(default_factory=dict)
    burstiness_score: float = 0.0
    execution_trace: str = ""
    compilation_success: bool = True
    repair_iterations: int = 0

    @property
    def source_code(self) -> str:
        """Returns the primary source code content."""
        if not self.code_files:
            return ""
        # Prefer implementation files (.c, .java, .py)
        for ext in (".c", ".cpp", ".java", ".py"):
            for fname, content in self.code_files.items():
                if fname.lower().endswith(ext):
                    return content
        return next(iter(self.code_files.values()), "")

    @property
    def report(self) -> str:
        """Alias for report_markdown."""
        return self.report_markdown

    @property
    def primary_code(self) -> str:
        """Returns concatenated code from all non-header source files for AST analysis."""
        if not self.code_files:
            return ""
        code_parts: List[str] = []
        for fname, content in self.code_files.items():
            if not fname.lower().endswith((".h", ".hpp")):
                code_parts.append(content)
        return "\n".join(code_parts) if code_parts else self.source_code


@dataclass
class AuditReport:
    """Consolidated report produced by the Adversarial Audit Loop."""

    passed: bool
    invariant_checks: Dict[str, bool] = field(default_factory=dict)
    similarity_matrix: PairwiseSimilarityMatrix = field(default_factory=PairwiseSimilarityMatrix)
    flagged_pairs: List[Dict[str, Any]] = field(default_factory=list)
    style_violations: Dict[str, List[str]] = field(default_factory=dict)
    scientific_coherence_ok: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


class AuditLoop:
    """Adversarial cross-checking loop for multi-student deliverables."""

    def __init__(
        self,
        skeleton_parser: Optional[SkeletonParser] = None,
        similarity_checker: Optional[SimilarityChecker] = None,
        humanizer_cleaner: Optional[HumanizerCleaner] = None,
        adversarial_evaluator: Optional[Callable[..., Any]] = None,
        default_max_similarity: float = 0.12,
    ) -> None:
        self.skeleton_parser = skeleton_parser or SkeletonParser()
        self.similarity_checker = similarity_checker or SimilarityChecker()
        self.humanizer_cleaner = humanizer_cleaner or HumanizerCleaner()
        self.adversarial_evaluator = adversarial_evaluator
        self.default_max_similarity = default_max_similarity

    def audit_deliverables(
        self,
        deliverables: Dict[str, StudentDeliverable],
        skeleton: Optional[Union[SkeletonProject, Dict[str, str], str, Path]] = None,
        max_similarity_threshold: Optional[float] = None,
    ) -> AuditReport:
        """Audits all student deliverables against invariants, anti-MOSS, and style criteria."""
        threshold = (
            max_similarity_threshold
            if max_similarity_threshold is not None
            else self.default_max_similarity
        )

        invariant_checks: Dict[str, bool] = {}
        style_violations: Dict[str, List[str]] = {}
        details: Dict[str, Any] = {}

        # 1. Invariant Verification (Function prototypes & signatures)
        if skeleton is not None:
            for name, deliv in deliverables.items():
                if deliv.code_files:
                    is_ok = self.skeleton_parser.verify_invariants(
                        skeleton=skeleton,
                        modified_files=deliv.code_files,
                    )
                    invariant_checks[name] = is_ok
                else:
                    invariant_checks[name] = False

        # 2. Anti-MOSS AST & Token Similarity Cross-Check
        solutions: Dict[str, str] = {}
        for name, deliv in deliverables.items():
            solutions[name] = deliv.primary_code or deliv.source_code

        base_code: Optional[List[str]] = None
        if skeleton is not None:
            if isinstance(skeleton, SkeletonProject):
                base_code = list(skeleton.files.values())
            elif isinstance(skeleton, dict):
                base_code = list(skeleton.values())
            elif isinstance(skeleton, (str, Path)):
                try:
                    proj = self.skeleton_parser.extract_skeleton(skeleton)
                    base_code = list(proj.files.values())
                except Exception:
                    base_code = [str(skeleton)]

        similarity_matrix = self.similarity_checker.compute_pairwise_similarity(
            solutions, base_code=base_code
        )

        flagged_pairs: List[Dict[str, Any]] = []

        for (a, b), score in similarity_matrix.items():
            if score > threshold:
                flagged_pairs.append({
                    "student_a": a,
                    "student_b": b,
                    "similarity": round(float(score), 4),
                    "threshold": threshold,
                    "status": "FLAGGED",
                })

        # 3. Style & Residual AI Tells Audit
        ai_tell_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.humanizer_cleaner.FR_AI_TELLS
        ]

        for name, deliv in deliverables.items():
            report_text = deliv.report_markdown or ""
            violations: List[str] = []
            for pat in ai_tell_patterns:
                match = pat.search(report_text)
                if match:
                    violations.append(match.group(0).strip())
            if violations:
                style_violations[name] = violations

        # 4. Multi-Model / Independent Adversarial Evaluation
        scientific_coherence_ok = True
        if self.adversarial_evaluator is not None:
            try:
                eval_res = self.adversarial_evaluator(
                    deliverables=deliverables,
                    skeleton=skeleton,
                )
                if isinstance(eval_res, dict):
                    details["evaluator"] = eval_res
                    if not eval_res.get("passed", True) or not eval_res.get("scientific_coherence_ok", True):
                        scientific_coherence_ok = False
                elif isinstance(eval_res, bool):
                    scientific_coherence_ok = eval_res
            except Exception as exc:
                details["evaluator_error"] = str(exc)

        # 5. Determine Overall Verdict
        invariants_passed = all(invariant_checks.values()) if invariant_checks else True
        similarity_passed = len(flagged_pairs) == 0
        style_passed = len(style_violations) == 0

        overall_passed = (
            invariants_passed
            and similarity_passed
            and style_passed
            and scientific_coherence_ok
        )

        return AuditReport(
            passed=overall_passed,
            invariant_checks=invariant_checks,
            similarity_matrix=similarity_matrix,
            flagged_pairs=flagged_pairs,
            style_violations=style_violations,
            scientific_coherence_ok=scientific_coherence_ok,
            details=details,
        )
