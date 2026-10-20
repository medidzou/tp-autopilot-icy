"""Comprehensive unit tests for SkeletonParser, SkeletonProject, and SubjectParser."""

import zipfile
from pathlib import Path
import pytest

from src.ingestion.parser import ParsedSubject, SubjectParser
from src.ingestion.skeleton import (
    FunctionSignature,
    SkeletonParser,
    SkeletonProject,
    TodoSlot,
)


def test_preserve_skeleton_signatures(tmp_path):
    """Verify preserving skeleton function signatures as specified in the brief."""
    parser = SkeletonParser()
    c_header = "int compute_checksum(const char *buffer, size_t len);\n"
    c_source = (
        "int compute_checksum(const char *buffer, size_t len) {\n"
        "    /* TODO: implement */\n"
        "    return 0;\n"
        "}\n"
    )

    project = parser.parse_files({"checksum.h": c_header, "checksum.c": c_source})
    assert len(project.todo_slots) == 1
    assert project.todo_slots[0].function_name == "compute_checksum"

    # Test valid implementation keeping signature
    valid_mod = {
        "checksum.c": "int compute_checksum(const char *buffer, size_t len) {\n    return 42;\n}\n"
    }
    assert project.validate_signatures(valid_mod) is True
    assert project.validate_signatures_preserved(valid_mod) is True

    # Test invalid modification breaking signature
    invalid_mod = {"checksum.c": "int compute_checksum(int bad_param) { return 0; }"}
    assert project.validate_signatures(invalid_mod) is False
    assert project.validate_signatures_preserved(invalid_mod) is False


def test_get_todo_locations_and_accessors():
    """Verify get_todo_locations, file listing, and signature accessors."""
    parser = SkeletonParser()
    files = {
        "utils.h": "void print_message(const char *msg);\n",
        "utils.c": (
            "#include \"utils.h\"\n"
            "// TODO: Global configuration setup\n"
            "void print_message(const char *msg) {\n"
            "    // TODO: implement printing\n"
            "    /* FIXME: handle NULL msg */\n"
            "}\n"
        ),
    }

    project = parser.parse_files(files)
    todos = project.get_todo_locations()
    assert len(todos) == 3

    # First TODO is at top level
    assert todos[0].function_name is None
    assert "Global configuration" in todos[0].todo_text

    # Next two TODOs are inside print_message
    assert todos[1].function_name == "print_message"
    assert todos[2].function_name == "print_message"

    # File accessors
    assert set(project.list_files()) == {"utils.h", "utils.c"}
    assert project.get_file("utils.h") == files["utils.h"]
    assert project.get_file("nonexistent.c") is None

    # Signatures
    h_sigs = project.get_function_signatures("utils.h")
    assert len(h_sigs) == 1
    assert h_sigs[0].name == "print_message"
    assert h_sigs[0].is_declaration is True
    assert h_sigs[0].return_type == "void"
    assert h_sigs[0].param_types == ["const char *"]


def test_signature_rejection_when_return_type_altered():
    """Verify modification that alters return type is rejected."""
    parser = SkeletonParser()
    c_source = "int compute_value(int a, int b) {\n    // TODO\n    return 0;\n}\n"
    project = parser.parse_files({"calc.c": c_source})

    # Return type changed from int to double
    bad_return = {"calc.c": "double compute_value(int a, int b) {\n    return 0.0;\n}\n"}
    assert project.validate_signatures(bad_return) is False


def test_signature_rejection_when_parameter_type_altered():
    """Verify modification that alters parameter types is rejected."""
    parser = SkeletonParser()
    c_source = "void process_data(char *data, size_t size) {\n    // TODO\n}\n"
    project = parser.parse_files({"proc.c": c_source})

    # Param size_t changed to int
    bad_param_type = {"proc.c": "void process_data(char *data, int size) {\n    // done\n}\n"}
    assert project.validate_signatures(bad_param_type) is False


def test_signature_rejection_when_function_deleted():
    """Verify modification that removes a mandatory function is rejected."""
    parser = SkeletonParser()
    c_source = (
        "int func_a(void) { /* TODO */ return 0; }\n"
        "int func_b(void) { /* TODO */ return 0; }\n"
    )
    project = parser.parse_files({"mod.c": c_source})

    # Only func_a is implemented, func_b missing completely
    missing_b = {"mod.c": "int func_a(void) { return 1; }\n"}
    assert project.validate_signatures(missing_b) is False


def test_signature_allows_extra_helper_functions():
    """Verify that adding new static or helper functions is permitted."""
    parser = SkeletonParser()
    c_source = "int run_task(int code) {\n    // TODO\n    return 0;\n}\n"
    project = parser.parse_files({"task.c": c_source})

    # Added static helper function
    extended_code = (
        "static int internal_helper(int x) {\n"
        "    return x * 2;\n"
        "}\n\n"
        "int run_task(int code) {\n"
        "    return internal_helper(code);\n"
        "}\n"
    )
    mod = {"task.c": extended_code}
    assert project.validate_signatures(mod) is True


def test_c_pointers_and_struct_signatures():
    """Verify parsing C functions with struct pointers and multiple asterisks."""
    parser = SkeletonParser()
    c_header = (
        "struct list_node *create_node(int val);\n"
        "char **split_string(const char *str, char delimiter);\n"
    )
    c_source = (
        "struct list_node *create_node(int val) {\n"
        "    /* TODO: allocate */\n"
        "    return NULL;\n"
        "}\n"
        "char **split_string(const char *str, char delimiter) {\n"
        "    /* TODO: tokenize */\n"
        "    return NULL;\n"
        "}\n"
    )
    project = parser.parse_files({"str_utils.h": c_header, "str_utils.c": c_source})
    assert len(project.todo_slots) == 2

    node_sig = [s for s in project.get_function_signatures("str_utils.h") if s.name == "create_node"][0]
    assert node_sig.return_type == "struct list_node *"
    assert node_sig.param_types == ["int"]

    split_sig = [s for s in project.get_function_signatures("str_utils.h") if s.name == "split_string"][0]
    assert split_sig.return_type == "char **"
    assert split_sig.param_types == ["const char *", "char"]


def test_java_skeleton_parsing():
    """Verify parsing Java classes, methods, and signature enforcement."""
    parser = SkeletonParser()
    java_source = (
        "public class MatrixWorker {\n"
        "    public static int[][] multiply(int[][] a, int[][] b) {\n"
        "        // TODO: implement multiplication\n"
        "        return null;\n"
        "    }\n"
        "    public void logResult(String msg) {\n"
        "        /* TODO: print */\n"
        "    }\n"
        "}\n"
    )
    project = parser.parse_files({"MatrixWorker.java": java_source})
    assert len(project.todo_slots) == 2
    assert project.todo_slots[0].function_name == "multiply"
    assert project.todo_slots[1].function_name == "logResult"

    # Valid modification
    valid_java = {
        "MatrixWorker.java": (
            "public class MatrixWorker {\n"
            "    public static int[][] multiply(int[][] a, int[][] b) {\n"
            "        return new int[1][1];\n"
            "    }\n"
            "    public void logResult(String msg) {\n"
            "        System.out.println(msg);\n"
            "    }\n"
            "}\n"
        )
    }
    assert project.validate_signatures(valid_java) is True

    # Invalid modification (altered return type of multiply)
    invalid_java = {
        "MatrixWorker.java": (
            "public class MatrixWorker {\n"
            "    public static int multiply(int[][] a, int[][] b) {\n"
            "        return 0;\n"
            "    }\n"
            "}\n"
        )
    }
    assert project.validate_signatures(invalid_java) is False


def test_extract_skeleton_from_zip(tmp_path: Path):
    """Verify extracting and parsing skeleton project from a .zip archive."""
    zip_path = tmp_path / "tp_skeleton.zip"
    header_content = "int solve(int n);\n"
    source_content = "int solve(int n) {\n    /* TODO: calculate */\n    return 0;\n}\n"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("include/solve.h", header_content)
        zf.writestr("src/solve.c", source_content)
        zf.writestr("Makefile", "all:\n\tgcc -o solve src/solve.c\n")

    parser = SkeletonParser()
    project = parser.extract_skeleton(zip_path)

    assert "include/solve.h" in project.files
    assert "src/solve.c" in project.files
    assert len(project.todo_slots) == 1
    assert project.todo_slots[0].function_name == "solve"

    valid = {"src/solve.c": "int solve(int n) { return n * 42; }\n"}
    assert project.validate_signatures(valid) is True


def test_extract_skeleton_from_directory(tmp_path: Path):
    """Verify parsing a skeleton project directly from a directory."""
    project_dir = tmp_path / "skeleton_dir"
    project_dir.mkdir()
    (project_dir / "main.c").write_text(
        "int main(int argc, char **argv) {\n    // TODO: parse flags\n    return 0;\n}\n",
        encoding="utf-8",
    )

    parser = SkeletonParser()
    project = parser.extract_skeleton(project_dir)
    assert "main.c" in project.files
    assert len(project.todo_slots) == 1
    assert project.todo_slots[0].function_name == "main"


def test_extract_skeleton_nonexistent_raises(tmp_path: Path):
    """Verify FileNotFoundError is raised for non-existent archive."""
    parser = SkeletonParser()
    with pytest.raises(FileNotFoundError):
        parser.extract_skeleton(tmp_path / "does_not_exist.zip")


def test_extract_skeleton_zip_slip_defense(tmp_path: Path):
    """Verify that archives with path traversal entries do not extract dangerous paths."""
    zip_path = tmp_path / "malicious.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0")
        zf.writestr("/root/.bashrc", "evil=1")
        zf.writestr("safe_file.c", "int main(void) { return 0; }")

    parser = SkeletonParser()
    project = parser.extract_skeleton(zip_path)

    assert "safe_file.c" in project.files
    assert "../../etc/passwd" not in project.files
    assert "/root/.bashrc" not in project.files


def test_subject_parser_extracts_constraints_and_metadata():
    """Verify SubjectParser correctly extracts title, constraints, forbidden items, and matiere."""
    subject_md = """# TP3: Allocation dynamique et Sémaphores en Programmation Système

## Objectifs
- Comprendre les mécanismes de mémoire partagée.
- Manipuler les sémaphores POSIX pour la synchronisation.

## Consignes & Contraintes
- La compilation sans warning avec `-Wall -Wextra -Werror` est obligatoire.
- Le Makefile doit générer l'exécutable `serveur`.
- Vérifier l'absence de fuites mémoire avec `valgrind`.

## Interdictions
- L'utilisation de variables globales est strictement interdite.
- Résolution itérative imposée : récursion interdite.

## Fonctions à implémenter
- `int init_shared_buffer(size_t size)`
- `void producer_loop(int sem_id)`

## Rendu
- Rendre une archive `tp3_groupe.tar.gz` contenant les fichiers `.c`, `.h` et le `Makefile`.
"""
    parser = SubjectParser()
    parsed = parser.parse_text(subject_md)

    assert parsed.title.startswith("TP3: Allocation dynamique")
    assert parsed.matiere_hint == "prog_systeme"
    assert len(parsed.objectives) >= 1
    assert any("-Wall" in c for c in parsed.constraints)
    assert any("interdite" in f.lower() for f in parsed.forbidden_approaches)
    assert "init_shared_buffer" in parsed.required_functions
    assert "producer_loop" in parsed.required_functions
    assert any("archive" in d.lower() for d in parsed.deliverables)

    summary = parsed.summary()
    assert summary["matiere_hint"] == "prog_systeme"
    assert summary["constraints_count"] >= 2


def test_subject_parser_from_file(tmp_path: Path):
    """Verify SubjectParser reading directly from a file."""
    sub_file = tmp_path / "sujet.md"
    sub_file.write_text(
        "# TP1 Java POO\n\nContrainte obligatoire: respecter l'encapsulation.\n",
        encoding="utf-8",
    )
    parser = SubjectParser()
    parsed = parser.parse_file(sub_file)

    assert parsed.title == "TP1 Java POO"
    assert parsed.matiere_hint == "java_poo"
    assert len(parsed.constraints) >= 1


def test_subject_parser_empty_and_nonexistent(tmp_path: Path):
    """Verify SubjectParser handling of empty text and non-existent files."""
    parser = SubjectParser()
    parsed = parser.parse_text("", default_title="Fallback")
    assert parsed.title == "Fallback"
    assert parsed.raw_text == ""

    with pytest.raises(FileNotFoundError):
        parser.parse_file(tmp_path / "nonexistent.md")


def test_java_method_overloading_preservation():
    """Verify that overloaded Java methods with the same name do not collide during validation."""
    parser = SkeletonParser()
    java_code = (
        "public class LoggerService {\n"
        "    public void log(String msg) {\n"
        "        // TODO: log string\n"
        "    }\n"
        "    public void log(int code) {\n"
        "        // TODO: log integer code\n"
        "    }\n"
        "}\n"
    )
    project = parser.parse_files({"LoggerService.java": java_code})
    assert len(project.todo_slots) == 2
    assert project.todo_slots[0].function_name == "log"
    assert project.todo_slots[1].function_name == "log"

    # Valid modification keeping both overloads
    valid_mod = {
        "LoggerService.java": (
            "public class LoggerService {\n"
            "    public void log(String msg) {\n"
            "        System.out.println(msg);\n"
            "    }\n"
            "    public void log(int code) {\n"
            "        System.err.println(code);\n"
            "    }\n"
            "}\n"
        )
    }
    assert project.validate_signatures(valid_mod) is True

    # Invalid modification breaking one overload's parameter type
    invalid_mod = {
        "LoggerService.java": (
            "public class LoggerService {\n"
            "    public void log(String msg) {\n"
            "        System.out.println(msg);\n"
            "    }\n"
            "    public void log(double bad_type) {\n"
            "        System.err.println(bad_type);\n"
            "    }\n"
            "}\n"
        )
    }
    assert project.validate_signatures(invalid_mod) is False


def test_c_anonymous_struct_by_value_parameter():
    """Verify that anonymous struct passed by value without parameter name in header is parsed accurately."""
    parser = SkeletonParser()
    c_header = "void display(struct point);\nvoid update(union data);\n"
    c_source = (
        "void display(struct point pt) {\n"
        "    /* TODO: display point */\n"
        "}\n"
        "void update(union data d) {\n"
        "    /* TODO: update data */\n"
        "}\n"
    )
    project = parser.parse_files({"graphics.h": c_header, "graphics.c": c_source})

    # Verify header signature has correct compound type
    h_sigs = project.get_function_signatures("graphics.h")
    disp_sig = [s for s in h_sigs if s.name == "display"][0]
    assert disp_sig.param_types == ["struct point"]

    upd_sig = [s for s in h_sigs if s.name == "update"][0]
    assert upd_sig.param_types == ["union data"]

    # Verify implementation keeping signatures passes
    valid_mod = {
        "graphics.c": (
            "void display(struct point pt) { printf(\"%d\", pt.x); }\n"
            "void update(union data d) { d.val = 42; }\n"
        )
    }
    assert project.validate_signatures(valid_mod) is True

    # Verify implementation with broken struct type fails
    invalid_mod = {
        "graphics.c": (
            "void display(struct wrong_struct pt) { return; }\n"
            "void update(union data d) { return; }\n"
        )
    }
    assert project.validate_signatures(invalid_mod) is False

