"""Unit and integration tests for DivergenceMatrix and SimilarityChecker (Anti-MOSS)."""

import pytest
from src.divergence.matrix import DivergenceMatrix, StrategyDirective
from src.divergence.similarity import SimilarityChecker
from src.profiles.models import StudentProfile


def test_divergence_assigns_orthogonal_strategies():
    """Verify that DivergenceMatrix assigns distinct primary paradigms to 6 students."""
    dm = DivergenceMatrix()
    students = ["Marc", "Thomas", "Sophie", "Julien", "Lea", "Alex"]
    strategies = dm.assign_strategies(students)
    assert len(strategies) == 6
    # S'assurer que les stratégies allouées sont distinctes
    paradigms = [s.primary_paradigm for s in strategies.values()]
    assert len(set(paradigms)) >= 4


def test_similarity_checker_detects_duplicate_code():
    """Verify that AST/token similarity checker flags structurally identical code but separates divergent implementations."""
    checker = SimilarityChecker()
    code_a = "int sum(int *arr, int n) { int s = 0; for(int i=0; i<n; i++) s += arr[i]; return s; }"
    code_b = "int total(int *t, int len) { int acc = 0; for(int j=0; j<len; j++) acc += t[j]; return acc; }"
    code_diff = "int sum_rec(int *a, int n) { if (n <= 0) return 0; return a[0] + sum_rec(a+1, n-1); }"

    sim_high = checker.calculate_ast_similarity(code_a, code_b)
    sim_low = checker.calculate_ast_similarity(code_a, code_diff)
    assert sim_high > 0.70  # Même structure de boucle
    assert sim_low < 0.30   # Itératif vs récursif


def test_compute_pairwise_similarity():
    """Verify pairwise similarity matrix computation across multiple student solutions."""
    checker = SimilarityChecker()
    solutions = {
        "Marc": "int sum(int *arr, int n) { int s = 0; for(int i=0; i<n; i++) s += arr[i]; return s; }",
        "Thomas": "int total(int *t, int len) { int acc = 0; for(int j=0; j<len; j++) acc += t[j]; return acc; }",
        "Sophie": "int sum_rec(int *a, int n) { if (n <= 0) return 0; return a[0] + sum_rec(a+1, n-1); }",
        "Julien": "int calc(int *ptr, int count) { int res = 0; int *end = ptr + count; while(ptr < end) { res += *ptr; ptr++; } return res; }"
    }
    pairwise = checker.compute_pairwise_similarity(solutions)
    # 4 students -> 4 * 3 / 2 = 6 pairs
    assert len(pairwise) == 6
    # Marc and Thomas are structurally identical
    assert pairwise[("Marc", "Thomas")] > 0.70
    # Sophie (recursive) vs Marc (for-loop)
    assert pairwise[("Marc", "Sophie")] < 0.35
    # Pointer arithmetic (Julien) vs indexing (Marc)
    assert pairwise[("Julien", "Sophie")] < 0.35


def test_similarity_identical_and_whitespace_invariance():
    """Verify identical code has similarity 1.0 and comments/whitespace do not evade detection."""
    checker = SimilarityChecker()
    code_base = """
    int find_max(int *arr, int len) {
        int max = arr[0];
        for (int i = 1; i < len; i++) {
            if (arr[i] > max) {
                max = arr[i];
            }
        }
        return max;
    }
    """
    code_whitespace_comments = """
    // Function that searches for maximum
    int   find_max  (  int * arr ,   int len  )   {
        /* Temporary max variable */
        int max = arr[0];
        for (int i = 1; i < len; i++) { // Loop over array
            if (arr[i] > max) {
                max = arr[i];
            }
        }
        return max;
    }
    """
    assert checker.calculate_ast_similarity(code_base, code_base) == 1.0
    sim_commented = checker.calculate_ast_similarity(code_base, code_whitespace_comments)
    assert sim_commented >= 0.95


def test_similarity_edge_cases():
    """Verify handling of empty code, very short snippets, and completely distinct code."""
    checker = SimilarityChecker()
    assert checker.calculate_ast_similarity("", "") == 1.0
    assert checker.calculate_ast_similarity("int a = 1;", "") == 0.0
    assert checker.calculate_ast_similarity("", "int b = 2;") == 0.0

    code_math = "double area(double r) { return 3.14159 * r * r; }"
    code_sys = "void handle_sig(int s) { signal(s, SIG_IGN); exit(1); }"
    assert checker.calculate_ast_similarity(code_math, code_sys) < 0.20


def test_divergence_with_student_profiles():
    """Verify DivergenceMatrix accepts StudentProfile instances and respects profile preferences."""
    dm = DivergenceMatrix()
    profiles = [
        StudentProfile(
            name="Marc",
            style_preferences={"preferred_loop": "while", "naming_convention": "snake_case"},
            calibration_answers={"style_code": "J'utilise souvent while et pointeurs."}
        ),
        StudentProfile(
            name="Sophie",
            style_preferences={"preferred_loop": "for", "naming_convention": "camelCase"},
            calibration_answers={"style_code": "J'adore la récursion et le découpage modulaire."}
        ),
        StudentProfile(name="Thomas"),
        StudentProfile(name="Julien"),
        StudentProfile(name="Lea"),
        StudentProfile(name="Alex"),
    ]
    strategies = dm.assign_strategies(profiles)
    assert len(strategies) == 6
    assert "Marc" in strategies
    assert isinstance(strategies["Marc"], StrategyDirective)
    assert strategies["Marc"].student_name == "Marc"
    # Verify preferences were reflected
    assert strategies["Marc"].naming_convention == "snake_case"
    assert strategies["Sophie"].naming_convention == "camelCase"


def test_divergence_respects_subject_constraints():
    """Verify that if the TP subject forbids recursion, recursive strategies are eliminated."""
    dm = DivergenceMatrix()
    students = ["Marc", "Thomas", "Sophie", "Julien", "Lea", "Alex"]
    
    # Subject explicitly forbids recursion
    strategies = dm.assign_strategies(
        students,
        subject_constraints=["Interdiction formelle d'utiliser la récursion", "Résolution itérative obligatoire"]
    )
    for name, directive in strategies.items():
        assert "recursive" not in directive.primary_paradigm.lower()
        assert directive.loop_style != "recursion"
        assert "récursion" not in directive.prompt_instructions.lower() or "sans récursion" in directive.prompt_instructions.lower()


def test_divergence_strategy_directive_has_detailed_guidelines():
    """Verify that StrategyDirective includes rich orthogonal dimensions and prompt guidance."""
    dm = DivergenceMatrix()
    directive = dm.assign_strategies(["Marc"])["Marc"]
    
    assert directive.primary_paradigm != ""
    assert directive.loop_style in {"for", "while", "do_while", "recursion", "pointer_iteration"}
    assert directive.memory_style in {"array_indexing", "pointer_arithmetic", "cursor_offset", "dynamic_stack", "buffer_window"}
    assert directive.modularity in {"static_helpers", "monolithic_inline", "utility_macros", "separated_logic"}
    assert directive.naming_convention in {"snake_case", "camelCase", "short_single_letter", "descriptive_verbose"}
    assert len(directive.prompt_instructions) > 20


def test_verify_anti_moss_threshold():
    """Verify detection of anti-MOSS compliance (< 12% pairwise similarity)."""
    checker = SimilarityChecker()
    # 3 divergent solutions
    safe_solutions = {
        "Etudiant1": "int sum_iter(int *t, int n) { int s = 0; for(int i=0; i<n; i++) s += t[i]; return s; }",
        "Etudiant2": "int sum_rec(int *a, int n) { if (n <= 0) return 0; return a[0] + sum_rec(a+1, n-1); }",
        "Etudiant3": "void log_error(const char *msg) { fprintf(stderr, \"[ERR]: %s\\n\", msg); exit(1); }"
    }
    is_safe, flagged = checker.verify_threshold(safe_solutions, max_threshold=0.35)
    assert is_safe is True
    assert len(flagged) == 0

    # Adding a copycat solution
    plagiarized_solutions = dict(safe_solutions)
    plagiarized_solutions["Etudiant4"] = "int sum_acc(int *tab, int size) { int acc = 0; for(int k=0; k<size; k++) acc += tab[k]; return acc; }"
    is_safe_2, flagged_2 = checker.verify_threshold(plagiarized_solutions, max_threshold=0.50)
    assert is_safe_2 is False
    assert len(flagged_2) >= 1
    pair_names = {(item["student_a"], item["student_b"]) for item in flagged_2}
    assert ("Etudiant1", "Etudiant4") in pair_names or ("Etudiant4", "Etudiant1") in pair_names


def test_pairwise_matrix_bidirectional_indexing():
    """Verify PairwiseSimilarityMatrix supports lookup with both (a, b) and (b, a)."""
    checker = SimilarityChecker()
    solutions = {
        "Marc": "int f1(void) { return 1; }",
        "Thomas": "int f2(void) { return 2; }"
    }
    pairwise = checker.compute_pairwise_similarity(solutions)
    # Test 'in' operator (__contains__) bidirectionally
    assert ("Marc", "Thomas") in pairwise
    assert ("Thomas", "Marc") in pairwise
    assert ("Inconnu", "Marc") not in pairwise
    assert pairwise[("Marc", "Thomas")] == pairwise[("Thomas", "Marc")]
    assert pairwise.get(("Thomas", "Marc")) is not None
    assert pairwise.get(("Inconnu", "Marc")) is None
    with pytest.raises(KeyError):
        _ = pairwise[("Inconnu", "Marc")]


def test_winnowing_similarity():
    """Verify Stanford Winnowing fingerprint calculation and similarity."""
    checker = SimilarityChecker()
    code_a = "int sum(int *arr, int n) { int s = 0; for(int i=0; i<n; i++) s += arr[i]; return s; }"
    code_b = "int total(int *t, int len) { int acc = 0; for(int j=0; j<len; j++) acc += t[j]; return acc; }"
    code_diff = "void print_banner(void) { puts(\"=== ICy TP System ===\"); }"

    winnow_sim_high = checker.calculate_winnowing_similarity(code_a, code_b, k=4, w=4)
    winnow_sim_low = checker.calculate_winnowing_similarity(code_a, code_diff, k=4, w=4)
    assert winnow_sim_high == 1.0
    assert winnow_sim_low < 0.20


def test_java_ast_similarity():
    """Verify SimilarityChecker on Java classes and methods."""
    checker = SimilarityChecker()
    java_iter = """
    public class DataProcessor {
        public int sumList(List<Integer> list) {
            int total = 0;
            for (int val : list) {
                total += val;
            }
            return total;
        }
    }
    """
    java_copy = """
    public class NumberCalculator {
        public int computeTotal(List<Integer> elements) {
            int acc = 0;
            for (int x : elements) {
                acc += x;
            }
            return acc;
        }
    }
    """
    java_diff = """
    public class LoggerService {
        public void writeLog(String message) {
            System.err.println("[WARN] " + message);
        }
    }
    """
    assert checker.calculate_ast_similarity(java_iter, java_copy) > 0.70
    assert checker.calculate_ast_similarity(java_iter, java_diff) < 0.25


def test_strategy_matrix_summary():
    """Verify DivergenceMatrix summary metrics calculation."""
    dm = DivergenceMatrix()
    students = ["Marc", "Thomas", "Sophie", "Julien", "Lea", "Alex"]
    strategies = dm.assign_strategies(students)
    summary = dm.get_strategy_matrix_summary(strategies)

    assert summary["total_students"] == 6
    assert summary["distinct_paradigms"] >= 4
    assert summary["distinct_loops"] >= 3
    assert summary["distinct_memories"] >= 3
    assert summary["distinct_namings"] >= 2
    assert summary["is_highly_orthogonal"] is True


def test_divergence_matrix_various_student_counts():
    """Verify DivergenceMatrix works with 1, 2, and more than 6 students."""
    dm = DivergenceMatrix()
    
    # Single student
    s1 = dm.assign_strategies(["Marc"])
    assert len(s1) == 1
    assert "Marc" in s1

    # 2 students
    s2 = dm.assign_strategies(["Marc", "Thomas"])
    assert len(s2) == 2
    assert s2["Marc"].primary_paradigm != s2["Thomas"].primary_paradigm

    # 8 students (cycles and maintains directives)
    names = [f"Student_{i}" for i in range(8)]
    s8 = dm.assign_strategies(names)
    assert len(s8) == 8
    paradigms = [s.primary_paradigm for s in s8.values()]
    assert len(set(paradigms)) >= 4


def test_calibration_answers_fallback_preference():
    """Verify calibration answers text clues are parsed when style_preferences is empty."""
    dm = DivergenceMatrix()
    profile = StudentProfile(
        name="Julien",
        calibration_answers={"style_code": "J'utilise des pointeurs et la convention camelCase"}
    )
    strategies = dm.assign_strategies([profile])
    julien = strategies["Julien"]
    assert julien.naming_convention == "camelCase"
    assert julien.memory_style == "pointer_arithmetic"
    # Ensure original profile.style_preferences was not mutated in-place
    assert profile.style_preferences == {}
