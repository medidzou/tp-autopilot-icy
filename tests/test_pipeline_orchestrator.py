"""Tests for Batch Pipeline Orchestrator and Adversarial Audit Loop (Task 7).

Verifies:
- Two-phase batch architecture: single core_solver call, parallel branch_solver calls.
- Integration of StudentProfile, StrategyDirective, HumanizerCleaner, and BurstinessScorer.
- BuildExecutor integration with real terminal trace capture and targeted auto-repair loop (up to 2 iterations).
- Adversarial Audit Loop: function signature preservation, anti-MOSS similarity threshold (< 12%),
  residual AI tells detection, and strategy re-routing.
- Full 6-student batch execution within < 180 seconds.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.builder.executor import BuildExecutor, BuildResult, ExecutionResult
from src.divergence import AntiMossSimilarityChecker, DivergenceMatrix, PairwiseSimilarityMatrix, StrategyDirective
from src.humanizer.burstiness import BurstinessScorer
from src.humanizer.cleaner import HumanizerCleaner
from src.ingestion.skeleton import SkeletonParser
from src.orchestrator.audit import AuditLoop, AuditReport, StudentDeliverable
from src.orchestrator.pipeline import BatchPipeline, BatchResult
from src.profiles.manager import ProfileManager
from src.profiles.models import StudentProfile


# ---------------------------------------------------------------------------
# Test Fixtures & Dummy Solvers
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_subject_text() -> str:
    return (
        "# TP 3 : Table de hachage en C\n"
        "Matière : Langage C\n"
        "Objectifs : Implémenter une table de hachage avec résolution par chaînage.\n"
        "Prototypes obligatoires :\n"
        "unsigned int hash_string(const char *str);\n"
        "int hash_table_insert(HashTable *ht, const char *key, int value);\n"
    )


@pytest.fixture
def sample_skeleton_files() -> Dict[str, str]:
    return {
        "hash.h": (
            "#ifndef HASH_H\n"
            "#define HASH_H\n"
            "typedef struct HashTable HashTable;\n"
            "unsigned int hash_string(const char *str);\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value);\n"
            "#endif\n"
        ),
        "hash.c": (
            '#include "hash.h"\n'
            "// TODO: implement hash_string\n"
            "unsigned int hash_string(const char *str) {\n"
            "    return 0;\n"
            "}\n"
            "// TODO: implement hash_table_insert\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    return 0;\n"
            "}\n"
        ),
    }


def make_c_code_for_student(student_name: str, variant_id: int = 1) -> str:
    """Generates distinct C code snippets so pairwise AST similarity remains < 12%."""
    if variant_id == 1:
        return (
            '#include "hash.h"\n'
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "struct BucketNode {\n"
            "    char key_buf[48];\n"
            "    int val_num;\n"
            "    struct BucketNode *next_ptr;\n"
            "};\n"
            "static unsigned int djb2_step(unsigned int h, unsigned char c) {\n"
            "    return ((h << 5) + h) + c;\n"
            "}\n"
            "unsigned int hash_string(const char *str) {\n"
            "    if (!str) return 0U;\n"
            "    unsigned int acc = 5381U;\n"
            "    const unsigned char *p = (const unsigned char *)str;\n"
            "    while (*p != 0) {\n"
            "        acc = djb2_step(acc, *p);\n"
            "        p++;\n"
            "    }\n"
            "    return acc;\n"
            "}\n"
            "static struct BucketNode *create_node(const char *k, int v) {\n"
            "    struct BucketNode *n = (struct BucketNode *)malloc(sizeof(struct BucketNode));\n"
            "    if (!n) return NULL;\n"
            "    int idx = 0;\n"
            "    while (k[idx] && idx < 47) {\n"
            "        n->key_buf[idx] = k[idx];\n"
            "        idx++;\n"
            "    }\n"
            "    n->key_buf[idx] = '\\0';\n"
            "    n->val_num = v;\n"
            "    n->next_ptr = NULL;\n"
            "    return n;\n"
            "}\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    if (!ht || !key) return -1;\n"
            "    struct BucketNode *entry = create_node(key, value);\n"
            "    if (!entry) return -2;\n"
            "    unsigned int slot = hash_string(key);\n"
            "    (void)slot;\n"
            "    return 0;\n"
            "}\n"
        )
    elif variant_id == 2:
        return (
            '#include "hash.h"\n'
            "#include <stdint.h>\n"
            "#include <stdbool.h>\n"
            "#define FNV_PRIME 16777619U\n"
            "#define FNV_SEED 2166136261U\n"
            "typedef struct {\n"
            "    uint32_t hash_val;\n"
            "    float occupancy;\n"
            "    bool active;\n"
            "} TableSlot;\n"
            "unsigned int hash_string(const char *str) {\n"
            "    uint32_t h = FNV_SEED;\n"
            "    for (size_t i = 0; str && str[i]; ++i) {\n"
            "        h ^= (uint8_t)str[i];\n"
            "        h *= FNV_PRIME;\n"
            "    }\n"
            "    return (unsigned int)h;\n"
            "}\n"
            "static int probe_quadratic(HashTable *t, uint32_t val, int payload) {\n"
            "    int outcome = -99;\n"
            "    for (size_t iter = 0; iter < 32; ++iter) {\n"
            "        size_t cell = (val + iter * iter) % 128;\n"
            "        if (cell > 0) {\n"
            "            outcome = (int)cell;\n"
            "            break;\n"
            "        }\n"
            "    }\n"
            "    return outcome;\n"
            "}\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    int final_status = 0;\n"
            "    if (ht == NULL) {\n"
            "        final_status = -1;\n"
            "    } else if (key == NULL) {\n"
            "        final_status = -1;\n"
            "    } else {\n"
            "        uint32_t h = hash_string(key);\n"
            "        final_status = probe_quadratic(ht, h, value);\n"
            "    }\n"
            "    return final_status;\n"
            "}\n"
        )
    elif variant_id == 3:
        return (
            '#include "hash.h"\n'
            "#include <string.h>\n"
            "typedef struct TreeNode {\n"
            "    int item_key;\n"
            "    int data;\n"
            "    struct TreeNode *left;\n"
            "    struct TreeNode *right;\n"
            "} TreeNode;\n"
            "static unsigned int fold_recursive(const char *s, unsigned int acc) {\n"
            "    if (!s || *s == '\\0') return acc;\n"
            "    unsigned int rotated = (acc << 7) | (acc >> 25);\n"
            "    return fold_recursive(s + 1, rotated ^ (unsigned char)(*s));\n"
            "}\n"
            "unsigned int hash_string(const char *str) {\n"
            "    return fold_recursive(str, 0x12345678U);\n"
            "}\n"
            "static int tree_insert(TreeNode **r, int v) {\n"
            "    if (*r == NULL) return 1;\n"
            "    if (v < (*r)->data) return tree_insert(&((*r)->left), v);\n"
            "    return tree_insert(&((*r)->right), v);\n"
            "}\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    if (ht == NULL || key == NULL) return -1;\n"
            "    TreeNode *dummy = NULL;\n"
            "    return tree_insert(&dummy, value);\n"
            "}\n"
        )
    elif variant_id == 4:
        return (
            '#include "hash.h"\n'
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    int res = -1;\n"
            "    if (ht) {\n"
            "        if (key) {\n"
            "            unsigned int u = hash_string(key);\n"
            "            int p = 0;\n"
            "            do {\n"
            "                int q = (int)((u + (unsigned int)(p * 13)) & 0x7F);\n"
            "                if (q > 0) {\n"
            "                    res = q;\n"
            "                    break;\n"
            "                }\n"
            "                p++;\n"
            "            } while (p < 16);\n"
            "        }\n"
            "    }\n"
            "    return res;\n"
            "}\n"
            "unsigned int hash_string(const char *str) {\n"
            "    if (!str || *str == 0) return 0;\n"
            "    unsigned int s = 0;\n"
            "    int x = 0;\n"
            "    do {\n"
            "        s ^= ((unsigned int)(unsigned char)str[x] << (x % 24));\n"
            "        x++;\n"
            "    } while (str[x] != '\\0');\n"
            "    return s;\n"
            "}\n"
        )
    elif variant_id == 5:
        return (
            '#include "hash.h"\n'
            "#include <stdlib.h>\n"
            "#include <assert.h>\n"
            "typedef struct {\n"
            "    char *stored_str;\n"
            "    long entry_id;\n"
            "    double weight;\n"
            "} EntryCell;\n"
            "unsigned int hash_string(const char *str) {\n"
            "    unsigned int hash = 0;\n"
            "    for (size_t i = 0; str && str[i]; ++i) {\n"
            "        hash += (unsigned char)str[i];\n"
            "        hash += (hash << 10);\n"
            "        hash ^= (hash >> 6);\n"
            "    }\n"
            "    hash += (hash << 3);\n"
            "    hash ^= (hash >> 11);\n"
            "    hash += (hash << 15);\n"
            "    return hash;\n"
            "}\n"
            "static EntryCell *allocate_table_block(size_t count) {\n"
            "    return (EntryCell *)calloc(count, sizeof(EntryCell));\n"
            "}\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    assert(ht != NULL);\n"
            "    assert(key != NULL);\n"
            "    EntryCell *block = allocate_table_block(16);\n"
            "    if (!block) return -2;\n"
            "    free(block);\n"
            "    return (int)(hash_string(key) % 16);\n"
            "}\n"
        )
    else:
        return (
            '#include "hash.h"\n'
            "#include <stdint.h>\n"
            "static uint32_t murmur_fmix(uint32_t h) {\n"
            "    h ^= h >> 16;\n"
            "    h *= 0x85ebca6b;\n"
            "    h ^= h >> 13;\n"
            "    h *= 0xc2b2ae35;\n"
            "    h ^= h >> 16;\n"
            "    return h;\n"
            "}\n"
            "unsigned int hash_string(const char *str) {\n"
            "    uint32_t h = 0x9747b28c;\n"
            "    for (const char *s = str; s && *s; ++s) {\n"
            "        uint32_t k = (uint8_t)(*s);\n"
            "        k *= 0xcc9e2d51;\n"
            "        k = (k << 15) | (k >> 17);\n"
            "        k *= 0x1b873593;\n"
            "        h ^= k;\n"
            "        h = (h << 13) | (h >> 19);\n"
            "        h = h * 5 + 0xe6546b64;\n"
            "    }\n"
            "    return (unsigned int)murmur_fmix(h);\n"
            "}\n"
            "int hash_table_insert(HashTable *ht, const char *key, int value) {\n"
            "    int code = -1;\n"
            "    if (ht != NULL && key != NULL) {\n"
            "        uint32_t m = hash_string(key);\n"
            "        code = (int)(m % 256);\n"
            "    }\n"
            "    return code;\n"
            "}\n"
        )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_pipeline_runs_core_then_branches(sample_subject_text):
    """Phase 1 runs core_solver ONCE; Phase 2 runs branch_solver for each student."""
    mock_core = MagicMock(return_value={"core_algorithm": "djb2_hash"})
    student_variant_map = {"Marc": 1, "Thomas": 2}
    mock_branch = MagicMock(side_effect=lambda student_name, **kwargs: {
        "code": make_c_code_for_student(student_name, variant_id=student_variant_map.get(student_name, 1)),
        "report": f"# Rapport de {student_name}\nImplémentation de la table de hachage en C.",
    })

    pipeline = BatchPipeline(core_solver=mock_core, branch_solver=mock_branch)
    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Marc", "Thomas"],
    )

    assert result.success is True
    assert len(result.student_deliverables) == 2
    assert "Marc" in result.student_deliverables
    assert "Thomas" in result.student_deliverables
    assert mock_core.call_count == 1
    assert mock_branch.call_count == 2
    assert isinstance(result.similarity_matrix, PairwiseSimilarityMatrix)
    assert isinstance(result.audit_report, AuditReport)
    assert result.duration_sec >= 0.0


def test_pipeline_integrates_profiles_and_divergence_directives(tmp_path, sample_subject_text):
    """Verifies each student branch receives their StudentProfile and StrategyDirective."""
    pm = ProfileManager(storage_dir=tmp_path / "profiles")
    pm.create_or_update_profile("Alice", samples=["J'utilise des pointeurs systématiquement."])
    pm.create_or_update_profile("Bob", samples=["Je préfère l'indexation par tableaux."])

    captured_args = {}

    def custom_branch(student_name, **kwargs):
        captured_args[student_name] = kwargs
        return {
            "code": make_c_code_for_student(student_name, 1 if student_name == "Alice" else 2),
            "report": f"Rapport technique de {student_name}.",
        }

    pipeline = BatchPipeline(
        profile_manager=pm,
        branch_solver=custom_branch,
        core_solver=lambda **kw: {"core": "hash"},
    )
    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Alice", "Bob"],
    )

    assert result.success is True
    assert "Alice" in captured_args and "Bob" in captured_args
    assert isinstance(captured_args["Alice"].get("profile"), StudentProfile)
    assert isinstance(captured_args["Alice"].get("directive"), StrategyDirective)
    assert captured_args["Alice"]["profile"].name == "Alice"
    assert captured_args["Bob"]["profile"].name == "Bob"
    # Ensure directives are distinct/orthogonal
    assert captured_args["Alice"]["directive"].primary_paradigm != captured_args["Bob"]["directive"].primary_paradigm


def test_pipeline_humanizes_reports_and_computes_burstiness(sample_subject_text):
    """Verifies that AI tells are purged from reports and burstiness metrics are calculated."""
    dirty_report = (
        "Il convient de noter que la fonction hash_string est optimale. "
        "En outre, force est de constater que malloc alloue la mémoire correctement. "
        "Il est crucial de souligner que nous gérons NULL."
    )

    mock_branch = MagicMock(return_value={
        "code": make_c_code_for_student("Lucas", 1),
        "report": dirty_report,
    })

    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"core": "hash"},
        branch_solver=mock_branch,
    )
    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Lucas"],
    )

    assert result.success is True
    deliverable = result.student_deliverables["Lucas"]
    # AI tells should be removed
    assert "Il convient de noter que" not in deliverable.report_markdown
    assert "force est de constater que" not in deliverable.report_markdown
    # Technical sanctuary preserved
    assert "malloc" in deliverable.report_markdown
    assert "NULL" in deliverable.report_markdown
    # Burstiness metrics must be populated
    assert "sentence_variance" in deliverable.burstiness_metrics
    assert deliverable.burstiness_score > 0.0


def test_pipeline_build_and_test_captures_traces(sample_subject_text, sample_skeleton_files):
    """BuildExecutor runs build_and_test; real traces stdout/stderr are captured in the deliverable."""
    mock_executor = MagicMock(spec=BuildExecutor)
    mock_build_result = BuildResult(
        success=True,
        exit_code=0,
        stdout="gcc -Wall -Wextra -Werror -pedantic -std=c11 -c hash.c\nCompilation finished.",
        stderr="",
        warnings_count=0,
        errors_count=0,
        execution_result=ExecutionResult(
            exit_code=0,
            stdout="Hash output: 15392019\nTest passed 100%",
            stderr="",
            command=["./test_bin"],
            duration_sec=0.012,
        ),
    )
    mock_executor.build_and_test.return_value = mock_build_result

    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"algo": "djb2"},
        branch_solver=lambda student_name, **kw: {
            "code_files": {"hash.c": make_c_code_for_student(student_name, 1), "hash.h": sample_skeleton_files["hash.h"]},
            "report": "Mon rapport avec les tests effectués.",
        },
        build_executor=mock_executor,
    )

    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Claire"],
        skeleton_files=sample_skeleton_files,
    )

    assert result.success is True
    deliv = result.student_deliverables["Claire"]
    assert mock_executor.build_and_test.call_count == 1
    assert deliv.compilation_success is True
    assert "Hash output: 15392019" in deliv.execution_trace or "Compilation finished." in deliv.execution_trace
    # Report must have execution traces injected
    assert "Trace d'Exécution" in deliv.report_markdown or "Compilation Trace" in deliv.report_markdown


def test_pipeline_auto_repair_on_build_failure(sample_subject_text, sample_skeleton_files):
    """When compilation fails initially, auto-repair triggers up to 2 iterations and succeeds."""
    attempt_counter = {"count": 0}

    def failing_then_working_branch(student_name, **kwargs):
        attempt_counter["count"] += 1
        repair_context = kwargs.get("repair_context")
        if repair_context:
            # Fixed code without syntax error
            return {
                "code": make_c_code_for_student(student_name, 1),
                "report": "Rapport corrigé après warning résolu.",
            }
        # Initial bugged code
        return {
            "code": 'int syntax_error( { return 0; }',
            "report": "Rapport initial avec erreur.",
        }

    mock_executor = MagicMock(spec=BuildExecutor)
    # 1st call fails, 2nd call succeeds
    fail_res = BuildResult(
        success=False,
        exit_code=1,
        stdout="",
        stderr="hash.c:1:19: error: expected identifier before '{' token",
        errors_count=1,
    )
    success_res = BuildResult(
        success=True,
        exit_code=0,
        stdout="Compilation successful.",
        stderr="",
        warnings_count=0,
        errors_count=0,
    )
    mock_executor.build_and_test.side_effect = [fail_res, success_res]

    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"core": "ok"},
        branch_solver=failing_then_working_branch,
        build_executor=mock_executor,
        max_repair_iterations=2,
    )

    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Devin"],
        skeleton_files=sample_skeleton_files,
    )

    assert result.success is True
    deliv = result.student_deliverables["Devin"]
    assert deliv is not None
    assert deliv.compilation_success is True
    assert deliv.repair_iterations == 1
    assert mock_executor.build_and_test.call_count == 2


def test_audit_loop_verifies_skeleton_invariants(sample_skeleton_files):
    """AuditLoop catches function signature alterations and passes strictly preserved prototypes."""
    audit = AuditLoop()
    skeleton_parser = SkeletonParser()
    skeleton_proj = skeleton_parser.parse_files(sample_skeleton_files)

    # Deliverable 1: Invariants strictly preserved
    valid_code = make_c_code_for_student("Alice", 1)
    deliv_valid = StudentDeliverable(
        student_name="Alice",
        code_files={"hash.c": valid_code, "hash.h": sample_skeleton_files["hash.h"]},
        report_markdown="# Rapport Alice\nAnalyse du code.",
    )

    # Deliverable 2: Return type altered (unsigned int -> void)
    invalid_code = (
        '#include "hash.h"\n'
        "void hash_string(const char *str) { return; }\n"
        "int hash_table_insert(HashTable *ht, const char *key, int value) { return 0; }\n"
    )
    deliv_invalid = StudentDeliverable(
        student_name="Bob",
        code_files={"hash.c": invalid_code, "hash.h": sample_skeleton_files["hash.h"]},
        report_markdown="# Rapport Bob\nAnalyse du code.",
    )

    report_valid = audit.audit_deliverables({"Alice": deliv_valid}, skeleton=skeleton_proj)
    assert report_valid.passed is True
    assert report_valid.invariant_checks.get("Alice") is True

    report_invalid = audit.audit_deliverables({"Bob": deliv_invalid}, skeleton=skeleton_proj)
    assert report_invalid.passed is False
    assert report_invalid.invariant_checks.get("Bob") is False


def test_audit_loop_detects_residual_ai_tells():
    """AuditLoop flags deliverables with residual AI clichés."""
    audit = AuditLoop()
    deliv_dirty = StudentDeliverable(
        student_name="Charlie",
        code_files={"main.c": "int main(void) { return 0; }"},
        report_markdown="Il convient de noter que le programme fonctionne parfaitement.",
    )

    report = audit.audit_deliverables({"Charlie": deliv_dirty})
    assert report.passed is False
    assert "Charlie" in report.style_violations
    assert len(report.style_violations["Charlie"]) > 0


def test_audit_loop_anti_moss_threshold_and_rerouting(sample_subject_text):
    """When 2 students share high similarity (> 12%), audit flags collision and pipeline reroutes."""
    # Alice and Bob initially get identical code
    identical_code = make_c_code_for_student("Common", 1)
    rerouted_code = make_c_code_for_student("Common", 3)

    call_records = []

    def mock_branch(student_name, **kwargs):
        directive = kwargs.get("directive")
        call_records.append((student_name, directive.primary_paradigm if directive else None))
        is_rerouted = kwargs.get("is_reroute", False)
        if is_rerouted and student_name == "Bob":
            return {"code": rerouted_code, "report": "Rapport ré-orienté."}
        return {"code": identical_code, "report": "Rapport initial."}

    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"core": "hash"},
        branch_solver=mock_branch,
    )

    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Alice", "Bob"],
    )

    assert result.success is True
    # Bob should have been re-routed
    matrix = result.similarity_matrix
    pair_sim = matrix.get(("Alice", "Bob"))
    assert pair_sim is not None
    assert pair_sim < 0.12
    assert result.audit_report.passed is True


def test_pipeline_6_students_batch_under_180s(sample_subject_text, sample_skeleton_files):
    """Runs a complete 6-student cohort generation and verifies execution time < 180 seconds."""
    student_cohort = ["Lucas", "Emma", "Thomas", "Chloé", "Maxime", "Léa"]

    def cohort_branch_solver(student_name, **kwargs):
        idx = student_cohort.index(student_name) + 1
        return {
            "code_files": {
                "hash.c": make_c_code_for_student(student_name, variant_id=idx),
                "hash.h": sample_skeleton_files["hash.h"],
            },
            "report": f"# Rapport de TP - {student_name}\n"
                      f"Implémentation conforme du sujet pour l'étudiant {student_name}.\n"
                      f"Les tests valident le dimensionnement et la distribution uniforme des clés.",
        }

    start_clock = time.time()
    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"algorithm": "hash_chains"},
        branch_solver=cohort_branch_solver,
    )

    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=student_cohort,
        skeleton_files=sample_skeleton_files,
    )
    elapsed = time.time() - start_clock

    assert result.success is True
    assert len(result.student_deliverables) == 6
    assert result.duration_sec < 180.0
    assert elapsed < 180.0

    # Pairwise similarity for all 15 pairs must be < 12%
    matrix = result.similarity_matrix
    for a in student_cohort:
        for b in student_cohort:
            if a < b:
                sim = matrix.get((a, b))
                assert sim is not None, f"Missing similarity for ({a}, {b})"
                assert sim < 0.12, f"Anti-MOSS violation between {a} and {b}: {sim:.2%}"


def test_pipeline_run_batch_alias(sample_subject_text):
    """Verifies that run_batch() is a fully functional alias for execute_session()."""
    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"core": "djb2"},
        branch_solver=lambda name, **kw: {
            "code": make_c_code_for_student(name, 1),
            "report": f"Rapport de {name}.",
        },
    )
    result = pipeline.run_batch(
        subject_text=sample_subject_text,
        student_names=["Marc"],
    )
    assert isinstance(result, BatchResult)
    assert result.success is True
    assert "Marc" in result.student_deliverables


def test_skeleton_parser_verify_invariants(sample_skeleton_files):
    """Verifies SkeletonParser.verify_invariants directly as class method and instance method."""
    parser = SkeletonParser()
    valid_files = {
        "hash.c": make_c_code_for_student("Alice", 1),
        "hash.h": sample_skeleton_files["hash.h"],
    }
    invalid_files = {
        "hash.c": "int unknown_func(void) { return 0; }",
        "hash.h": sample_skeleton_files["hash.h"],
    }

    # Instance method
    assert parser.verify_invariants(sample_skeleton_files, valid_files) is True
    assert parser.verify_invariants(sample_skeleton_files, invalid_files) is False

    # Class method
    assert SkeletonParser.verify_invariants(sample_skeleton_files, valid_files) is True
    assert SkeletonParser.verify_invariants(sample_skeleton_files, invalid_files) is False


def test_anti_moss_similarity_checker_alias():
    """Verifies AntiMossSimilarityChecker is available and aliases SimilarityChecker."""
    checker = AntiMossSimilarityChecker()
    code_a = "int sum(int a, int b) { return a + b; }"
    code_b = "int add(int x, int y) { return x + y; }"
    sim = checker.calculate_ast_similarity(code_a, code_b)
    assert 0.0 <= sim <= 1.0


def test_cross_file_subject_prototype_invariant_enforcement(sample_subject_text):
    """Verifies that prototypes extracted into subject_prototypes.h are strictly enforced in main.c."""
    parser = SkeletonParser()
    skeleton = {"subject_prototypes.h": "unsigned int hash_string(const char *str);\nint hash_table_insert(HashTable *ht, const char *key, int value);"}

    # Correct implementation in main.c matching header prototypes across files
    valid_impl = {
        "main.c": make_c_code_for_student("Alice", 1),
    }
    assert parser.verify_invariants(skeleton, valid_impl) is True

    # Altered implementation (wrong return type in main.c)
    invalid_impl = {
        "main.c": "int hash_string(const char *str) { return 0; }\nint hash_table_insert(HashTable *ht, const char *key, int value) { return 0; }",
    }
    assert parser.verify_invariants(skeleton, invalid_impl) is False

    # Missing implementation in main.c
    missing_impl = {
        "main.c": "int helper(void) { return 42; }",
    }
    assert parser.verify_invariants(skeleton, missing_impl) is False


def test_typing_reflection_get_type_hints():
    """Verifies that runtime type inspection on BatchPipeline does not raise NameError due to missing typing imports."""
    import typing
    hints = typing.get_type_hints(BatchPipeline._normalize_branch_output)
    assert "return" in hints


def test_multi_student_rerouting_assigns_distinct_templates(sample_subject_text):
    """When multiple students collide simultaneously, rerouting assigns distinct strategy templates."""
    identical_code = make_c_code_for_student("Common", 1)

    reroute_directives = {}

    def mock_branch(student_name, **kwargs):
        is_rerouted = kwargs.get("is_reroute", False)
        directive = kwargs.get("directive")
        if is_rerouted and directive:
            reroute_directives[student_name] = directive.primary_paradigm
            # Return distinct variants on reroute
            idx = 2 if student_name == "Bob" else 3
            return {"code": make_c_code_for_student(student_name, idx), "report": "Rerouted."}
        return {"code": identical_code, "report": "Initial identical code."}

    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"core": "hash"},
        branch_solver=mock_branch,
    )

    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Alice", "Bob", "Charlie"],
    )

    # Bob and Charlie collided with Alice and each other, so both should be rerouted
    assert "Bob" in reroute_directives
    assert "Charlie" in reroute_directives
    # Crucially, Bob and Charlie must NOT receive the same paradigm template
    assert reroute_directives["Bob"] != reroute_directives["Charlie"]


def test_pipeline_timeout_enforcement(sample_subject_text):
    """Verifies that execute_session fails when execution duration exceeds timeout."""
    def slow_worker(student_name, **kwargs):
        time.sleep(0.15)
        return {"code": make_c_code_for_student(student_name, 1), "report": "Slow report."}

    pipeline = BatchPipeline(
        core_solver=lambda **kw: {"core": "hash"},
        branch_solver=slow_worker,
    )

    # Timeout set to 0.05s, which is smaller than slow_worker sleep duration
    result = pipeline.execute_session(
        subject_text=sample_subject_text,
        student_names=["Alice"],
        timeout=0.05,
    )
    assert result.success is False


def test_auto_course_detection_applied_when_matiere_id_none():
    """Verifies that when matiere_id=None is passed, syllabus detector resolves the course ID and applies it."""
    captured_kwargs = {}

    def mock_core_solver(**kwargs):
        captured_kwargs["core_matiere_id"] = kwargs.get("matiere_id")
        return {"core": "hash"}

    def mock_branch_solver(student_name, **kwargs):
        captured_kwargs["branch_matiere_id"] = kwargs.get("matiere_id")
        return {
            "code": f"// Code for {student_name}\nint main(void) {{ return 0; }}\n",
            "report": f"# Rapport {student_name}\nContenu",
        }

    pipeline = BatchPipeline(
        core_solver=mock_core_solver,
        branch_solver=mock_branch_solver,
    )

    subject_with_keywords = (
        "# TP Langage C : Pointeurs et Allocation Dynamique\n"
        "Dans ce TP de langage C, nous allons manipuler les pointeurs et faire du malloc et free."
    )

    result = pipeline.execute_session(
        subject_text=subject_with_keywords,
        student_names=["Lucas"],
        matiere_id=None,
    )

    assert result.success is True
    assert captured_kwargs.get("core_matiere_id") == "langage_c"
    assert captured_kwargs.get("branch_matiere_id") == "langage_c"
    assert result.subject_info == "langage_c"


