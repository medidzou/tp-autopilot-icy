"""Tests for the strict build executor and real execution trace capture."""

import os
import sys
import pytest
from pathlib import Path

from src.builder.executor import BuildExecutor, BuildResult, ExecutionResult


def test_c_strict_build_success(tmp_path):
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\nclean:\n\trm -f test_bin test_bin.exe\n"
    c_code = "int main(void) { return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)
    
    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert result.success is True
    assert result.warnings_count == 0
    assert result.exit_code == 0


def test_c_strict_build_fails_on_warning(tmp_path):
    executor = BuildExecutor()
    # Code with unused variable triggering an error with -Werror
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\n"
    c_code = "int main(void) { int unused = 42; return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)
    
    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert result.success is False
    assert "error: unused variable" in result.stderr
    assert result.exit_code != 0


def test_c_direct_compilation_without_makefile(tmp_path):
    """When no Makefile is provided, compile directly using syllabus flags."""
    executor = BuildExecutor()
    c_code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    printf(\"Direct compilation OK\\n\");\n"
        "    return 0;\n"
        "}\n"
    )
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c", run_binary=True)
    assert result.success is True
    assert result.warnings_count == 0
    assert result.execution_result is not None
    assert "Direct compilation OK" in result.execution_result.stdout


def test_c_direct_compilation_fails_on_strict_warning(tmp_path):
    """Direct compilation must enforce strict flags (-Werror) and fail on warnings."""
    executor = BuildExecutor()
    c_code = (
        "int main(void) {\n"
        "    int unused_val = 100;\n"
        "    return 0;\n"
        "}\n"
    )
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert result.success is False
    assert "error: unused variable" in result.stderr


def test_run_binary_and_capture_stdout_stderr(tmp_path):
    """Verifies binary execution captures exact stdout, stderr, and return code."""
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o app main.c\n"
    c_code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    fprintf(stdout, \"Hello from stdout!\\n\");\n"
        "    fprintf(stderr, \"Hello from stderr!\\n\");\n"
        "    return 0;\n"
        "}\n"
    )
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c", run_binary=True)
    assert result.success is True
    assert result.execution_result is not None
    assert "Hello from stdout!" in result.execution_result.stdout
    assert "Hello from stderr!" in result.execution_result.stderr
    assert result.execution_result.exit_code == 0


def test_run_binary_with_stdin_feed(tmp_path):
    """Executes compiled binary feeding stdin input and verifying calculation."""
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o calc main.c\n"
    c_code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    int a, b;\n"
        "    if (scanf(\"%d %d\", &a, &b) == 2) {\n"
        "        printf(\"SUM=%d\\n\", a + b);\n"
        "    }\n"
        "    return 0;\n"
        "}\n"
    )
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(
        str(tmp_path),
        matiere_id="langage_c",
        run_binary=True,
        binary_stdin="15 27\n"
    )
    assert result.success is True
    assert result.execution_result is not None
    assert "SUM=42" in result.execution_result.stdout


def test_execution_trace_formatting_for_report(tmp_path):
    """Formatted trace must contain build command, return code, and execution output for report injection."""
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o demo main.c\n"
    c_code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    printf(\"Trace test execution step\\n\");\n"
        "    return 0;\n"
        "}\n"
    )
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c", run_binary=True)
    report_trace = result.get_report_trace()
    assert "### Compilation Trace" in report_trace
    assert "Exit Code: 0" in report_trace
    assert "### Execution Trace" in report_trace
    assert "Trace test execution step" in report_trace


def test_clean_target_execution(tmp_path):
    """Verifies that clean_project executes make clean successfully."""
    executor = BuildExecutor()
    makefile = (
        "all:\n\tgcc -Wall -Wextra -Werror -o artifact main.c\n"
        "clean:\n\trm -f artifact artifact.exe\n"
    )
    c_code = "int main(void) { return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    build_res = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert build_res.success is True

    # Check executable was created
    binary_exists = (tmp_path / "artifact").exists() or (tmp_path / "artifact.exe").exists()
    assert binary_exists is True

    clean_res = executor.clean(str(tmp_path))
    assert clean_res.success is True


def test_nonexistent_directory_fails_gracefully():
    executor = BuildExecutor()
    result = executor.build_and_test("/path/that/does/not/exist/anywhere", matiere_id="langage_c")
    assert result.success is False
    assert "does not exist" in result.stderr.lower()


def test_warning_detection_without_werror(tmp_path):
    """When a build produces warnings without -Werror, warnings_count must be detected."""
    executor = BuildExecutor()
    # Makefile without -Werror but with -Wall
    makefile = "all:\n\tgcc -Wall -o test_bin main.c\n"
    c_code = "int main(void) { int unused = 42; return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c", strict_warnings=False)
    assert result.warnings_count >= 1
    assert "warning:" in result.stderr.lower() or "unused variable" in result.stderr.lower()


def test_valgrind_check_fallback_behavior(tmp_path):
    """Checks valgrind analysis: if valgrind is absent, reports unavailable gracefully without crashing."""
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\n"
    c_code = "int main(void) { return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c", run_valgrind=True)
    assert result.success is True
    # If valgrind is not on system, valgrind_executed is False or valgrind_report indicates status
    if not executor.has_valgrind():
        assert result.valgrind_clean is None
        assert "not found" in (result.valgrind_report or "").lower()


def test_binary_execution_timeout(tmp_path):
    """Programs with infinite loops must time out safely without hanging the process."""
    executor = BuildExecutor()
    c_code = (
        "int main(void) {\n"
        "    while (1) { /* infinite loop */ }\n"
        "    return 0;\n"
        "}\n"
    )
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(
        str(tmp_path),
        matiere_id="langage_c",
        run_binary=True,
        timeout=1.0,
    )
    assert result.success is False
    assert result.execution_result is not None
    assert "timed out" in result.execution_result.stderr.lower()


def test_c_syntax_error_build_failure(tmp_path):
    """Syntax errors must fail the build, populate errors_count and stderr."""
    executor = BuildExecutor()
    c_code = "int main(void) { invalid_c_syntax!!! return 0; }\n"
    (tmp_path / "main.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert result.success is False
    assert result.errors_count >= 1
    assert "error:" in result.stderr.lower()


def test_java_direct_compilation_and_execution(tmp_path):
    """Java source files are compiled with javac -Xlint:all and executable with java."""
    executor = BuildExecutor()
    java_code = (
        "public class Solution {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(\"Java POO Execution Verified\");\n"
        "    }\n"
        "}\n"
    )
    (tmp_path / "Solution.java").write_text(java_code)

    result = executor.build_and_test(
        str(tmp_path),
        matiere_id="java_poo",
        run_binary=True,
        binary_name="Solution",
    )
    assert result.success is True
    assert result.warnings_count == 0
    assert result.execution_result is not None
    assert "Java POO Execution Verified" in result.execution_result.stdout


def test_clean_directory_without_makefile(tmp_path):
    """Direct compiled files (*.o, *.exe, *.class) are cleaned even without a Makefile."""
    executor = BuildExecutor()
    c_code = "int main(void) { return 0; }\n"
    (tmp_path / "main.c").write_text(c_code)

    build_res = executor.build_and_test(str(tmp_path), matiere_id="langage_c")
    assert build_res.success is True
    assert any(tmp_path.glob("*.exe")) or (tmp_path / "test_bin").exists()

    clean_res = executor.clean(str(tmp_path))
    assert clean_res.success is True
    assert not any(tmp_path.glob("*.exe"))
    assert not (tmp_path / "test_bin").exists()


def test_python_pytest_success(tmp_path):
    """Python projects run pytest automatically, capturing test results and traces."""
    executor = BuildExecutor()
    test_code = (
        "def test_arithmetic():\n"
        "    assert 20 + 22 == 42\n"
    )
    (tmp_path / "test_example.py").write_text(test_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="python")
    assert result.success is True
    assert result.exit_code == 0
    assert result.errors_count == 0
    assert "passed" in result.stdout.lower()
    report_trace = result.get_report_trace()
    assert "### Compilation Trace" in report_trace
    assert "pytest" in report_trace


def test_python_pytest_failure(tmp_path):
    """Failing pytest tests must mark result as failure and increment errors_count."""
    executor = BuildExecutor()
    test_code = (
        "def test_intentional_fail():\n"
        "    assert 1 == 2, 'Value mismatch intentional failure'\n"
    )
    (tmp_path / "test_broken.py").write_text(test_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="python")
    assert result.success is False
    assert result.exit_code != 0
    assert result.errors_count >= 1
    assert "failed" in result.stdout.lower() or "assertionerror" in result.stdout.lower()


def test_python_binary_execution_with_stdin(tmp_path):
    """Python scripts can be executed directly as binaries with args and stdin."""
    executor = BuildExecutor()
    script_code = (
        "import sys\n"
        "data = sys.stdin.read().strip()\n"
        "print(f'Processed: {data.upper()}')\n"
    )
    (tmp_path / "main.py").write_text(script_code)

    result = executor.build_and_test(
        str(tmp_path),
        matiere_id="python",
        run_binary=True,
        binary_name="main",
        binary_stdin="telecom sudparis\n",
    )
    assert result.execution_result is not None
    assert result.execution_result.success is True
    assert "Processed: TELECOM SUDPARIS" in result.execution_result.stdout


def test_valgrind_forwards_binary_args(tmp_path, monkeypatch):
    """Valgrind command must include binary_args if provided."""
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\n"
    c_code = "int main(int argc, char **argv) { (void)argc; (void)argv; return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    captured_cmds = []

    def mock_run(cmd, *args, **kwargs):
        captured_cmds.append(list(cmd))
        import subprocess
        # Fake return for valgrind
        if cmd and cmd[0] == "valgrind":
            return subprocess.CompletedProcess(cmd, 0, stdout="clean", stderr="ERROR SUMMARY: 0 errors")
        # Run real build command
        return subprocess.run.__wrapped__(cmd, *args, **kwargs) if hasattr(subprocess.run, "__wrapped__") else orig_run(cmd, *args, **kwargs)

    import subprocess
    orig_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(executor, "has_valgrind", lambda *args, **kwargs: True)

    result = executor.build_and_test(
        str(tmp_path),
        matiere_id="langage_c",
        run_valgrind=True,
        binary_args=["--verbose", "--port=8080"],
    )
    valgrind_calls = [c for c in captured_cmds if c and c[0] == "valgrind"]
    assert len(valgrind_calls) == 1
    assert "--verbose" in valgrind_calls[0]
    assert "--port=8080" in valgrind_calls[0]
    assert result.valgrind_clean is True


def test_timeout_preservation_not_capped_at_ten_seconds(tmp_path, monkeypatch):
    """Explicit timeout parameter (e.g. 45.0s) must not be arbitrarily capped at 10.0s."""
    executor = BuildExecutor()
    makefile = "all:\n\tgcc -Wall -Wextra -Werror -o test_bin main.c\n"
    c_code = "int main(void) { return 0; }\n"
    (tmp_path / "Makefile").write_text(makefile)
    (tmp_path / "main.c").write_text(c_code)

    passed_timeouts = []

    def mock_execute_binary(binary_path, args=None, stdin_data=None, timeout=None):
        passed_timeouts.append(timeout)
        return ExecutionResult(exit_code=0, stdout="ok", stderr="")

    monkeypatch.setattr(executor, "execute_binary", mock_execute_binary)

    result = executor.build_and_test(
        str(tmp_path),
        matiere_id="langage_c",
        run_binary=True,
        timeout=45.0,
    )
    assert result.success is True
    assert len(passed_timeouts) == 1
    assert passed_timeouts[0] == 45.0


def test_recursive_source_globbing_in_src_directory(tmp_path):
    """Direct compilation must locate source files in subdirectories such as src/."""
    executor = BuildExecutor()
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    c_code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    printf(\"Recursive globbing successful\\n\");\n"
        "    return 0;\n"
        "}\n"
    )
    (src_dir / "app.c").write_text(c_code)

    result = executor.build_and_test(str(tmp_path), matiere_id="langage_c", run_binary=True)
    assert result.success is True
    assert result.execution_result is not None
    assert "Recursive globbing successful" in result.execution_result.stdout


def test_interpreted_and_script_projects_build_success(tmp_path):
    """SQL, Bash, Web, and data deliverables compile/validate successfully without binary compilation."""
    executor = BuildExecutor()
    (tmp_path / "queries.sql").write_text("SELECT id, name FROM students WHERE grade >= 10;\n")
    (tmp_path / "deploy.sh").write_text("#!/bin/bash\necho 'Starting server'\n")
    (tmp_path / "index.html").write_text("<!DOCTYPE html><html><body><h1>TP Web</h1></body></html>\n")

    result = executor.build_and_test(str(tmp_path), matiere_id="bdd")
    assert result.success is True
    assert result.errors_count == 0
    assert "sans compilation binaire" in result.stdout



