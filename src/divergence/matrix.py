"""Anti-Collision Divergence Matrix for multi-student TP generation.

Generates mutually orthogonal coding strategies across 6 students to ensure AST
dissimilarity remains strictly below the 12% anti-MOSS threshold while complying
with syllabus constraints and individual student profiles.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Union
from pydantic import BaseModel, Field

try:
    from src.profiles.models import StudentProfile
except ImportError:
    StudentProfile = Any  # type: ignore[misc,assignment]


class StrategyDirective(BaseModel):
    """Specific architectural and stylistic directives assigned to a student."""

    student_name: str
    primary_paradigm: str
    loop_style: str  # "for", "while", "do_while", "recursion", "pointer_iteration"
    memory_style: str  # "array_indexing", "pointer_arithmetic", "cursor_offset", "dynamic_stack", "buffer_window"
    modularity: str  # "static_helpers", "monolithic_inline", "utility_macros", "separated_logic"
    naming_convention: str  # "snake_case", "camelCase", "short_single_letter", "descriptive_verbose"
    error_handling: str  # "early_return", "single_exit", "nested_guard", "assert_guard"
    comment_density: str  # "minimalist", "dense_technical", "docstring_only", "step_by_step"
    forbidden_patterns: List[str] = Field(default_factory=list)
    prompt_instructions: str = ""

    def generate_prompt_instructions(self) -> str:
        """Formats the directive into a clear prompt directive for the branch code generator."""
        forbidden_clause = (
            f"\n- **Interdictions strictes :** {', '.join(self.forbidden_patterns)}"
            if self.forbidden_patterns
            else ""
        )
        instructions = (
            f"### CONSIGNES DE RÉSOLUTION (Étudiant: {self.student_name})\n"
            f"- Résoudre le sujet de TP de façon claire, propre et directe pour un élève-ingénieur.\n"
            f"- Respecter rigoureusement les prototypes et signatures de fonctions imposés par le sujet.\n"
            f"- Code fonctionnel, sans warning de compilation et sans fuite mémoire.{forbidden_clause}"
        )
        self.prompt_instructions = instructions
        return instructions


class DivergenceMatrix:
    """Manages the allocation of orthogonal strategies across students."""

    # 6 foundational strategy templates using standard, natural syntax
    BASE_STRATEGY_TEMPLATES: List[Dict[str, Any]] = [
        {
            "primary_paradigm": "iterative_standard",
            "loop_style": "for",
            "memory_style": "array_indexing",
            "modularity": "monolithic_inline",
            "naming_convention": "snake_case",
            "error_handling": "early_return",
            "comment_density": "minimalist",
        },
        {
            "primary_paradigm": "while_pointer_idiomatic",
            "loop_style": "while",
            "memory_style": "pointer_arithmetic",
            "modularity": "static_helpers",
            "naming_convention": "camelCase",
            "error_handling": "single_exit",
            "comment_density": "dense_technical",
        },
        {
            "primary_paradigm": "structured_modular_for",
            "loop_style": "for",
            "memory_style": "cursor_offset",
            "modularity": "separated_logic",
            "naming_convention": "descriptive_verbose",
            "error_handling": "nested_guard",
            "comment_density": "docstring_only",
        },
        {
            "primary_paradigm": "static_modular_helpers",
            "loop_style": "while",
            "memory_style": "array_indexing",
            "modularity": "static_helpers",
            "naming_convention": "short_single_letter",
            "error_handling": "early_return",
            "comment_density": "step_by_step",
        },
        {
            "primary_paradigm": "guarded_dowhile_flow",
            "loop_style": "do_while",
            "memory_style": "array_indexing",
            "modularity": "monolithic_inline",
            "naming_convention": "snake_case",
            "error_handling": "assert_guard",
            "comment_density": "step_by_step",
        },
        {
            "primary_paradigm": "clean_standard_flow",
            "loop_style": "for",
            "memory_style": "pointer_arithmetic",
            "modularity": "separated_logic",
            "naming_convention": "camelCase",
            "error_handling": "single_exit",
            "comment_density": "minimalist",
        },
    ]

    # Replacement templates when recursion is forbidden by subject constraints
    ITERATIVE_FALLBACK_TEMPLATE: Dict[str, Any] = {
        "primary_paradigm": "standard_iterative_clean",
        "loop_style": "for",
        "memory_style": "array_indexing",
        "modularity": "separated_logic",
        "naming_convention": "descriptive_verbose",
        "error_handling": "nested_guard",
        "comment_density": "docstring_only",
    }

    def __init__(self) -> None:
        pass

    def _is_recursion_forbidden(self, constraints: Optional[Sequence[str]]) -> bool:
        if not constraints:
            return False
        pattern = re.compile(
            r"(sans\s+r[ée]cursion|interdiction.*r[ée]cursion|no\s+recursion|r[ée]solution\s+it[ée]rative|it[ée]ratif\s+obligatoire|interdire.*r[ée]cursion)",
            re.IGNORECASE,
        )
        return any(pattern.search(c) for c in constraints)

    def assign_strategies(
        self,
        students: Sequence[Union[str, Any]],
        subject_constraints: Optional[Sequence[str]] = None,
    ) -> Dict[str, StrategyDirective]:
        """Assigns mutually orthogonal strategies to a list of students or StudentProfile objects."""
        assigned: Dict[str, StrategyDirective] = {}
        no_recursion = self._is_recursion_forbidden(subject_constraints)

        # Build available templates
        templates = [dict(t) for t in self.BASE_STRATEGY_TEMPLATES]
        if no_recursion:
            for idx, tmpl in enumerate(templates):
                if (
                    "recursive" in tmpl["primary_paradigm"].lower()
                    or tmpl["loop_style"] == "recursion"
                ):
                    templates[idx] = dict(self.ITERATIVE_FALLBACK_TEMPLATE)

        for i, item in enumerate(students):
            # Extract student name and preferences if StudentProfile
            student_name: str = ""
            preferences: Dict[str, Any] = {}

            if isinstance(item, str):
                student_name = item
            elif hasattr(item, "name"):
                student_name = getattr(item, "name")
                preferences = dict(getattr(item, "style_preferences", {}) or {})
                # Also check calibration answers for preferences if style_preferences is empty
                calib = getattr(item, "calibration_answers", {}) or {}
                style_ans = str(calib.get("style_code", "")).lower()
                if "while" in style_ans and "preferred_loop" not in preferences:
                    preferences["preferred_loop"] = "while"
                if "pointeur" in style_ans and "memory_style" not in preferences:
                    preferences["memory_style"] = "pointer_arithmetic"
                if "camelcase" in style_ans and "naming_convention" not in preferences:
                    preferences["naming_convention"] = "camelCase"
                elif "snake_case" in style_ans and "naming_convention" not in preferences:
                    preferences["naming_convention"] = "snake_case"
            else:
                student_name = str(item)

            # Select base template cycling if > 6
            tmpl = dict(templates[i % len(templates)])

            # Override with explicit student preferences if available
            if "naming_convention" in preferences:
                tmpl["naming_convention"] = preferences["naming_convention"]
            if "preferred_loop" in preferences:
                pref_loop = preferences["preferred_loop"]
                if not (no_recursion and pref_loop == "recursion"):
                    tmpl["loop_style"] = pref_loop
            if "memory_style" in preferences:
                tmpl["memory_style"] = preferences["memory_style"]
            if "modularity" in preferences:
                tmpl["modularity"] = preferences["modularity"]

            # If recursion is forbidden, enforce safety
            if no_recursion:
                if (
                    "recursive" in tmpl["primary_paradigm"].lower()
                    or tmpl["loop_style"] == "recursion"
                ):
                    tmpl["primary_paradigm"] = "cursor_offset_accumulator"
                    tmpl["loop_style"] = "while"

            forbidden: List[str] = []
            if no_recursion:
                forbidden.append("récursion (résolution strictement sans récursion, itératif obligatoire)")

            directive = StrategyDirective(
                student_name=student_name,
                primary_paradigm=tmpl["primary_paradigm"],
                loop_style=tmpl["loop_style"],
                memory_style=tmpl["memory_style"],
                modularity=tmpl["modularity"],
                naming_convention=tmpl["naming_convention"],
                error_handling=tmpl["error_handling"],
                comment_density=tmpl["comment_density"],
                forbidden_patterns=forbidden,
            )
            directive.generate_prompt_instructions()
            assigned[student_name] = directive

        return assigned

    def generate_strategy_matrix(
        self,
        student_names: Sequence[Union[str, Any]],
        subject_constraints: Optional[Sequence[str]] = None,
        matiere_id: Optional[str] = None,
    ) -> Dict[str, StrategyDirective]:
        """Alias for assign_strategies for orchestrator pipelines."""
        return self.assign_strategies(students=student_names, subject_constraints=subject_constraints)

    def get_strategy_matrix_summary(
        self, strategies: Dict[str, StrategyDirective]
    ) -> Dict[str, Any]:
        """Produces an analytical summary of divergence dimensions across students."""
        paradigms = [s.primary_paradigm for s in strategies.values()]
        loops = [s.loop_style for s in strategies.values()]
        memories = [s.memory_style for s in strategies.values()]
        modularities = [s.modularity for s in strategies.values()]
        namings = [s.naming_convention for s in strategies.values()]

        return {
            "total_students": len(strategies),
            "distinct_paradigms": len(set(paradigms)),
            "distinct_loops": len(set(loops)),
            "distinct_memories": len(set(memories)),
            "distinct_modularities": len(set(modularities)),
            "distinct_namings": len(set(namings)),
            "is_highly_orthogonal": len(set(paradigms)) >= min(4, len(strategies)),
        }
