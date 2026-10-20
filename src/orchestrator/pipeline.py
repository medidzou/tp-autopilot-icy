"""Batch Pipeline Orchestrator for Multi-Student TP Generation.

Implements:
1. Two-phase architecture:
   - Phase 1: Single algorithmic core solver call to eliminate 429 quota/rate limits.
   - Phase 2: Parallel decorrelated branch generators per student, injecting StudentProfile,
     StrategyDirective, HumanizerCleaner (with technical sanctuary), and BurstinessScorer.
2. Build validation via BuildExecutor:
   - Captures real execution stdout/stderr traces.
   - Targeted auto-repair loop (up to 2 iterations) on compilation error or warning.
3. Adversarial Audit Loop:
   - Invariant verification against skeleton prototypes.
   - Anti-MOSS AST & n-gram similarity cross-check across all students (< 12%).
   - Strategy re-routing when collision is detected.
4. Consolidated BatchResult under 180 seconds.
"""

from __future__ import annotations

import concurrent.futures
import copy
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from src.builder.executor import BuildExecutor, BuildResult
from src.divergence.matrix import DivergenceMatrix, StrategyDirective
from src.divergence.similarity import AntiMossSimilarityChecker, PairwiseSimilarityMatrix, SimilarityChecker
from src.humanizer.burstiness import BurstinessScorer
from src.humanizer.cleaner import HumanizerCleaner
from src.ingestion.skeleton import SkeletonParser, SkeletonProject
from src.orchestrator.audit import AuditLoop, AuditReport, StudentDeliverable
from src.profiles.manager import ProfileManager
from src.profiles.models import StudentProfile

try:
    from src.syllabus.detector import SyllabusDetector
    from src.syllabus.models import MatiereInfo
except ImportError:
    SyllabusDetector = None
    MatiereInfo = None


@dataclass
class BatchResult:
    """Consolidated result of a multi-student batch generation session."""

    success: bool
    student_deliverables: Dict[str, StudentDeliverable]
    similarity_matrix: PairwiseSimilarityMatrix
    audit_report: AuditReport
    duration_sec: float
    core_solution: Any = None
    subject_info: Optional[Any] = None


class BatchPipeline:
    """Orchestrates two-phase TP code and report generation across student cohorts."""

    def __init__(
        self,
        core_solver: Optional[Callable[..., Any]] = None,
        branch_solver: Optional[Callable[..., Any]] = None,
        profile_manager: Optional[ProfileManager] = None,
        skeleton_parser: Optional[SkeletonParser] = None,
        divergence_matrix: Optional[DivergenceMatrix] = None,
        build_executor: Optional[BuildExecutor] = None,
        humanizer_cleaner: Optional[HumanizerCleaner] = None,
        burstiness_scorer: Optional[BurstinessScorer] = None,
        audit_loop: Optional[AuditLoop] = None,
        syllabus_detector: Optional[Any] = None,
        max_workers: int = 6,
        max_repair_iterations: int = 2,
        max_reroute_iterations: int = 2,
    ) -> None:
        self.core_solver = core_solver
        self.branch_solver = branch_solver
        self.profile_manager = profile_manager or ProfileManager()
        self.skeleton_parser = skeleton_parser or SkeletonParser()
        self.divergence_matrix = divergence_matrix or DivergenceMatrix()
        self.build_executor = build_executor
        self.humanizer_cleaner = humanizer_cleaner or HumanizerCleaner()
        self.burstiness_scorer = burstiness_scorer or BurstinessScorer()
        self.audit_loop = audit_loop or AuditLoop(
            skeleton_parser=self.skeleton_parser,
            similarity_checker=AntiMossSimilarityChecker(),
            humanizer_cleaner=self.humanizer_cleaner,
        )
        self.syllabus_detector = syllabus_detector
        if self.syllabus_detector is None and SyllabusDetector is not None:
            try:
                self.syllabus_detector = SyllabusDetector()
            except Exception:
                self.syllabus_detector = None

        self.max_workers = max_workers
        self.max_repair_iterations = max_repair_iterations
        self.max_reroute_iterations = max_reroute_iterations

    def _run_core_solver(
        self,
        subject_text: str,
        skeleton: Optional[Dict[str, str]],
        matiere_id: Optional[str],
    ) -> Any:
        """Executes the single common core algorithmic solver call (Phase 1)."""
        if self.core_solver is None:
            return {"core_algorithm": "standard_solution", "subject": subject_text}

        kwargs = {
            "subject_text": subject_text,
            "skeleton": skeleton,
            "matiere_id": matiere_id,
        }

        try:
            return self.core_solver(**kwargs)
        except TypeError:
            pass

        try:
            return self.core_solver(subject_text)
        except TypeError:
            return self.core_solver()

    def _run_branch_solver(
        self,
        student_name: str,
        core_solution: Any,
        profile: StudentProfile,
        directive: StrategyDirective,
        subject_text: str,
        skeleton: Optional[Dict[str, str]],
        matiere_id: Optional[str],
        repair_context: Optional[Dict[str, Any]] = None,
        is_reroute: bool = False,
    ) -> Dict[str, Any]:
        """Calls branch_solver for a single student variant."""
        if self.branch_solver is None:
            return {
                "code": f"// Code for {student_name}\nint main(void) {{ return 0; }}\n",
                "report": f"# Rapport de TP - {student_name}\nExécution conforme aux directives.",
            }

        call_kwargs = {
            "student_name": student_name,
            "core_solution": core_solution,
            "profile": profile,
            "directive": directive,
            "subject_text": subject_text,
            "skeleton": skeleton,
            "matiere_id": matiere_id,
            "repair_context": repair_context,
            "is_reroute": is_reroute,
        }

        try:
            return self.branch_solver(**call_kwargs)
        except TypeError:
            pass

        try:
            return self.branch_solver(student_name, **call_kwargs)
        except TypeError:
            pass

        try:
            return self.branch_solver(student_name, core_solution, profile, directive)
        except TypeError:
            pass

        try:
            return self.branch_solver(student_name, core_solution)
        except TypeError:
            return self.branch_solver(student_name)

    def _normalize_branch_output(
        self,
        raw_output: Any,
        skeleton_files: Optional[Dict[str, str]],
        matiere_id: Optional[str],
    ) -> Tuple[Dict[str, str], str]:
        """Extracts code_files mapping and report markdown from diverse branch_solver outputs."""
        code_files: Dict[str, str] = {}
        report_text: str = ""

        if isinstance(raw_output, dict):
            if "code_files" in raw_output and isinstance(raw_output["code_files"], dict):
                code_files = dict(raw_output["code_files"])
            elif "code" in raw_output:
                code_val = raw_output["code"]
                if isinstance(code_val, dict):
                    code_files = dict(code_val)
                elif isinstance(code_val, str):
                    # Determine target filename
                    target_name = "main.c"
                    if skeleton_files:
                        for sname in skeleton_files:
                            if sname.endswith((".c", ".cpp", ".java", ".py")):
                                target_name = sname
                                break
                    elif matiere_id == "java_poo":
                        target_name = "Main.java"
                    elif matiere_id in ("python", "python_data"):
                        target_name = "main.py"
                    code_files = {target_name: code_val}

            report_text = raw_output.get("report") or raw_output.get("report_markdown") or ""

        elif isinstance(raw_output, (tuple, list)) and len(raw_output) >= 2:
            code_candidate = raw_output[0]
            if isinstance(code_candidate, dict):
                code_files = dict(code_candidate)
            else:
                code_files = {"main.c": str(code_candidate)}
            report_text = str(raw_output[1])

        elif isinstance(raw_output, str):
            code_files = {"main.c": raw_output}
            report_text = "# Rapport de TP\n\nCode implémenté."

        # If skeleton files are available, inject any missing header or helper files into code_files
        if skeleton_files:
            for sname, scontent in skeleton_files.items():
                if sname not in code_files and sname.endswith((".h", ".hpp", "Makefile")):
                    code_files[sname] = scontent

        return code_files, report_text

    def _generate_student_branch(
        self,
        student_name: str,
        core_solution: Any,
        profile: StudentProfile,
        directive: StrategyDirective,
        subject_text: str,
        skeleton_data: Optional[Dict[str, str]],
        matiere_id: Optional[str],
        is_reroute: bool = False,
    ) -> StudentDeliverable:
        """Executes Phase 2 branch generation, style cleaning, and burstiness scoring for a single student."""
        raw_output = self._run_branch_solver(
            student_name=student_name,
            core_solution=core_solution,
            profile=profile,
            directive=directive,
            subject_text=subject_text,
            skeleton=skeleton_data,
            matiere_id=matiere_id,
            is_reroute=is_reroute,
        )

        code_files, report_text = self._normalize_branch_output(
            raw_output=raw_output,
            skeleton_files=skeleton_data,
            matiere_id=matiere_id,
        )

        # Style cleaning and humanization (with technical sanctuary protection)
        cleaned_report = self.humanizer_cleaner.humanize_report(
            report_text=report_text,
            profile=profile,
        )

        # Statistical cadence & burstiness scoring
        b_metrics = self.burstiness_scorer.calculate_metrics(cleaned_report)
        b_score = self.burstiness_scorer.calculate_score(cleaned_report, profile=profile)

        deliverable = StudentDeliverable(
            student_name=student_name,
            code_files=code_files,
            report_markdown=cleaned_report,
            profile=profile,
            directive=directive,
            burstiness_metrics=b_metrics,
            burstiness_score=b_score,
        )

        return deliverable

    def _validate_and_build(
        self,
        deliverable: StudentDeliverable,
        core_solution: Any,
        subject_text: str,
        skeleton_data: Optional[Dict[str, str]],
        matiere_id: Optional[str],
    ) -> StudentDeliverable:
        """Runs BuildExecutor compilation and test checks, triggering targeted auto-repair if needed."""
        if self.build_executor is None:
            return deliverable

        with tempfile.TemporaryDirectory(prefix=f"tp_build_{deliverable.student_name}_") as tmpdir:
            tmppath = Path(tmpdir)

            # Write code files to temp directory
            for rel_name, content in deliverable.code_files.items():
                file_path = tmppath / rel_name
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

            # Run build and test
            build_res = self.build_executor.build_and_test(str(tmppath), matiere_id=matiere_id)

            # Auto-repair loop on compiler errors or strict warnings
            repair_iteration = 0
            while (not build_res.success or build_res.warnings_count > 0) and repair_iteration < self.max_repair_iterations:
                repair_iteration += 1
                repair_ctx = {
                    "errors": build_res.stderr,
                    "stdout": build_res.stdout,
                    "warnings": build_res.warnings_count,
                    "code_files": deliverable.code_files,
                }

                raw_repaired = self._run_branch_solver(
                    student_name=deliverable.student_name,
                    core_solution=core_solution,
                    profile=deliverable.profile or StudentProfile(name=deliverable.student_name),
                    directive=deliverable.directive or StrategyDirective(
                        student_name=deliverable.student_name,
                        primary_paradigm="iterative",
                        loop_style="for",
                        memory_style="array",
                        modularity="modular",
                        naming_convention="snake_case",
                        error_handling="return",
                        comment_density="normal",
                    ),
                    subject_text=subject_text,
                    skeleton=skeleton_data,
                    matiere_id=matiere_id,
                    repair_context=repair_ctx,
                )

                repaired_files, repaired_report = self._normalize_branch_output(
                    raw_output=raw_repaired,
                    skeleton_files=skeleton_data,
                    matiere_id=matiere_id,
                )

                deliverable.code_files = repaired_files
                if repaired_report:
                    deliverable.report_markdown = self.humanizer_cleaner.humanize_report(
                        repaired_report, profile=deliverable.profile
                    )
                    deliverable.burstiness_metrics = self.burstiness_scorer.calculate_metrics(
                        deliverable.report_markdown
                    )
                    deliverable.burstiness_score = self.burstiness_scorer.calculate_score(
                        deliverable.report_markdown, profile=deliverable.profile
                    )

                # Overwrite temp files with repaired code
                for rel_name, content in deliverable.code_files.items():
                    file_path = tmppath / rel_name
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content, encoding="utf-8")

                build_res = self.build_executor.build_and_test(str(tmppath), matiere_id=matiere_id)

            deliverable.build_result = build_res
            deliverable.compilation_success = build_res.success
            deliverable.repair_iterations = repair_iteration

            # Capture real execution traces and inject into the markdown report
            trace_repr = build_res.get_report_trace() if hasattr(build_res, "get_report_trace") else (build_res.stdout + "\n" + build_res.stderr)
            deliverable.execution_trace = trace_repr

            stdout_capture = (
                build_res.execution_result.stdout
                if build_res.execution_result
                else build_res.stdout
            )
            stderr_capture = (
                build_res.execution_result.stderr
                if build_res.execution_result
                else build_res.stderr
            )
            deliverable.report_markdown = self.humanizer_cleaner.inject_execution_trace(
                text=deliverable.report_markdown,
                stdout=stdout_capture or trace_repr,
                stderr=stderr_capture,
            )

        return deliverable

    def execute_session(
        self,
        subject_text: str,
        student_names: List[str],
        skeleton_files: Optional[Dict[str, str]] = None,
        skeleton_path: Optional[Union[str, Path]] = None,
        matiere_id: Optional[str] = None,
        timeout: float = 180.0,
    ) -> BatchResult:
        """Executes the complete two-phase batch generation, validation, and adversarial audit."""
        start_time = time.time()

        # Subject and course topic resolution
        detected_matiere_id = matiere_id
        if detected_matiere_id is None and self.syllabus_detector is not None:
            try:
                detected_info = self.syllabus_detector.detect_matiere(subject_text)
                detected_matiere_id = getattr(detected_info, "id", None)
            except Exception:
                detected_matiere_id = None

        # Skeleton ingestion
        skeleton_project: Optional[SkeletonProject] = None
        skeleton_data: Optional[Dict[str, str]] = skeleton_files

        if skeleton_files is not None:
            skeleton_project = self.skeleton_parser.parse_files(skeleton_files)
        elif skeleton_path is not None:
            skeleton_project = self.skeleton_parser.extract_skeleton(skeleton_path)
            skeleton_data = skeleton_project.files
        elif subject_text:
            # Extract any function prototypes declared in the subject text
            import re
            protos = re.findall(
                r"(?:[a-zA-Z_]\w*\s+)+(?:\*+\s*)?[a-zA-Z_]\w*\s*\([^;)]*\)\s*;",
                subject_text,
            )
            if protos:
                skeleton_data = {"subject_prototypes.h": "\n".join(protos)}


        # ---------------------------------------------------------------------
        # Phase 1: Noyau Commun (Single Core Algorithmic Solver Call)
        # ---------------------------------------------------------------------
        core_solution = self._run_core_solver(
            subject_text=subject_text,
            skeleton=skeleton_data,
            matiere_id=detected_matiere_id,
        )

        # Divergence strategy generation across student cohort
        student_entities = [
            self.profile_manager.get_profile(s)
            if self.profile_manager.profile_exists(s)
            else s
            for s in student_names
        ]
        strategy_matrix = self.divergence_matrix.generate_strategy_matrix(
            student_names=student_entities,
            matiere_id=detected_matiere_id,
        )


        # ---------------------------------------------------------------------
        # Phase 2: Parallel Branch Generators (Branches Parallèles Décorrélées)
        # ---------------------------------------------------------------------
        deliverables: Dict[str, StudentDeliverable] = {}

        def _worker_task(name: str) -> StudentDeliverable:
            # 1. Profile retrieval or initialization
            if self.profile_manager.profile_exists(name):
                profile = self.profile_manager.get_profile(name)
            else:
                profile = StudentProfile(name=name)

            directive = strategy_matrix.get(name) or StrategyDirective(
                student_name=name,
                primary_paradigm="iterative",
                loop_style="for",
                memory_style="array",
                modularity="modular",
                naming_convention="snake_case",
                error_handling="return",
                comment_density="normal",
            )

            deliv = self._generate_student_branch(
                student_name=name,
                core_solution=core_solution,
                profile=profile,
                directive=directive,
                subject_text=subject_text,
                skeleton_data=skeleton_data,
                matiere_id=detected_matiere_id,
            )

            if self.build_executor is not None:
                deliv = self._validate_and_build(
                    deliverable=deliv,
                    core_solution=core_solution,
                    subject_text=subject_text,
                    skeleton_data=skeleton_data,
                    matiere_id=detected_matiere_id,
                )

            return deliv

        worker_count = min(len(student_names), max(1, self.max_workers))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_student = {
                executor.submit(_worker_task, s_name): s_name
                for s_name in student_names
            }
            try:
                for future in concurrent.futures.as_completed(future_to_student, timeout=timeout):
                    deliv = future.result()
                    deliverables[deliv.student_name] = deliv
            except concurrent.futures.TimeoutError:
                # Handle timeout: mark any missing deliverables as incomplete
                for f, s_name in future_to_student.items():
                    if s_name not in deliverables:
                        deliverables[s_name] = StudentDeliverable(
                            student_name=s_name,
                            code_files={},
                            report_markdown="# Error: Timeout exceeded\nGeneration exceeded the maximum allowed duration.",
                            compilation_success=False,
                        )

        # ---------------------------------------------------------------------
        # Phase 3: Adversarial Audit Loop & Anti-Collision Re-Routing
        # ---------------------------------------------------------------------
        skeleton_ref = skeleton_project or skeleton_data
        audit_report = self.audit_loop.audit_deliverables(
            deliverables=deliverables,
            skeleton=skeleton_ref,
        )

        # Anti-MOSS collision re-routing loop (ré-aiguillage)
        reroute_count = 0
        while audit_report.flagged_pairs and reroute_count < self.max_reroute_iterations:
            reroute_count += 1
            colliding_students = sorted(list({pair["student_b"] for pair in audit_report.flagged_pairs}))

            for idx, s_name in enumerate(colliding_students):
                curr_deliv = deliverables[s_name]
                template_idx = (
                    reroute_count * len(colliding_students) + idx + 3
                ) % len(DivergenceMatrix.BASE_STRATEGY_TEMPLATES)
                alt_template = DivergenceMatrix.BASE_STRATEGY_TEMPLATES[template_idx]

                alt_directive = StrategyDirective(
                    student_name=s_name,
                    primary_paradigm=alt_template["primary_paradigm"],
                    loop_style=alt_template["loop_style"],
                    memory_style=alt_template["memory_style"],
                    modularity=alt_template["modularity"],
                    naming_convention=alt_template["naming_convention"],
                    error_handling=alt_template["error_handling"],
                    comment_density=alt_template["comment_density"],
                )
                alt_directive.generate_prompt_instructions()

                rerouted_deliv = self._generate_student_branch(
                    student_name=s_name,
                    core_solution=core_solution,
                    profile=curr_deliv.profile or StudentProfile(name=s_name),
                    directive=alt_directive,
                    subject_text=subject_text,
                    skeleton_data=skeleton_data,
                    matiere_id=detected_matiere_id,
                    is_reroute=True,
                )

                if self.build_executor is not None:
                    rerouted_deliv = self._validate_and_build(
                        deliverable=rerouted_deliv,
                        core_solution=core_solution,
                        subject_text=subject_text,
                        skeleton_data=skeleton_data,
                        matiere_id=detected_matiere_id,
                    )

                deliverables[s_name] = rerouted_deliv

            audit_report = self.audit_loop.audit_deliverables(
                deliverables=deliverables,
                skeleton=skeleton_ref,
            )

        duration = round(time.time() - start_time, 3)
        overall_success = (
            audit_report.passed
            and all(d.compilation_success for d in deliverables.values())
            and (duration <= timeout)
        )

        return BatchResult(
            success=overall_success,
            student_deliverables=deliverables,
            similarity_matrix=audit_report.similarity_matrix,
            audit_report=audit_report,
            duration_sec=duration,
            core_solution=core_solution,
            subject_info=detected_matiere_id,
        )

    def run_batch(
        self,
        subject_text: Optional[str] = None,
        student_names: Optional[List[str]] = None,
        subject_path: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> BatchResult:
        """Alias and file-path friendly wrapper around execute_session."""
        actual_subject_text = subject_text or ""
        if subject_path is not None:
            p = Path(subject_path)
            if p.exists() and p.is_file():
                actual_subject_text = p.read_text(encoding="utf-8")

        names = student_names or []
        return self.execute_session(
            subject_text=actual_subject_text,
            student_names=names,
            **kwargs,
        )
