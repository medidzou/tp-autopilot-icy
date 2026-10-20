"""Strict Build Executor & Real Trace Capture Engine for ICy 3A Practical Sessions.

This module automates the strict compilation and testing of student TP code
(Langage C, Programmation Système, Java & POO, Python / pytest). It enforces strict compiler flags
(-Wall -Wextra -Werror -pedantic -std=c11, -Xlint:all), detects warnings and errors,
executes compiled binaries and test runners with real I/O capture, and formats execution traces
suitable for injection into grading reports.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from src.syllabus.detector import SyllabusDetector
    from src.syllabus.models import MatiereInfo
except ImportError:
    SyllabusDetector = None
    MatiereInfo = None


@dataclass
class ExecutionResult:
    """Represents the real execution output of a compiled binary or test runner."""

    exit_code: int
    stdout: str
    stderr: str
    command: List[str] = field(default_factory=list)
    duration_sec: float = 0.0

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class BuildResult:
    """Result of a compilation and optional test/binary execution run."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    warnings_count: int = 0
    errors_count: int = 0
    command: List[str] = field(default_factory=list)
    execution_result: Optional[ExecutionResult] = None
    valgrind_clean: Optional[bool] = None
    valgrind_report: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)
    project_dir: str = ""

    def get_report_trace(self) -> str:
        """Formats real execution and build traces into clean Markdown for report injection."""
        lines: List[str] = []
        cmd_str = " ".join(self.command) if self.command else "build"

        lines.append("### Compilation Trace")
        lines.append(f"- Command: `{cmd_str}`")
        lines.append(f"- Exit Code: {self.exit_code}")
        lines.append(f"- Diagnostics: {self.warnings_count} warning(s), {self.errors_count} error(s)")

        full_build_output = (self.stdout + ("\n" + self.stderr if self.stderr else "")).strip()
        if full_build_output:
            lines.append("```terminal")
            lines.append(f"$ {cmd_str}")
            lines.append(full_build_output)
            lines.append("```")
        else:
            lines.append("```terminal")
            lines.append(f"$ {cmd_str}")
            lines.append("[No compiler output - clean build]")
            lines.append("```")

        if self.execution_result:
            exec_cmd = " ".join(self.execution_result.command)
            lines.append("\n### Execution Trace")
            lines.append(f"- Command: `{exec_cmd}`")
            lines.append(f"- Exit Code: {self.execution_result.exit_code}")
            lines.append(f"- Duration: {self.execution_result.duration_sec:.3f}s")
            
            exec_out = self.execution_result.stdout
            if self.execution_result.stderr:
                exec_out = (exec_out + ("\n[stderr]\n" + self.execution_result.stderr)).strip()

            lines.append("```terminal")
            lines.append(f"$ {exec_cmd}")
            if exec_out.strip():
                lines.append(exec_out.strip())
            else:
                lines.append("[Execution produced no output]")
            lines.append("```")

        if self.valgrind_report:
            lines.append("\n### Valgrind Memory Audit")
            status = "Clean (0 leaks, 0 errors)" if self.valgrind_clean else "Violations detected or audit skipped"
            lines.append(f"- Status: {status}")
            lines.append("```terminal")
            lines.append(self.valgrind_report.strip())
            lines.append("```")

        return "\n".join(lines)


class BuildExecutor:
    """Executes builds with strict compiler flags and captures real terminal traces."""

    DEFAULT_C_RULES: Dict[str, Any] = {
        "compiler": "gcc",
        "flags": ["-Wall", "-Wextra", "-Werror", "-pedantic", "-std=c11"],
        "build_tool": "make",
        "clean_command": "make clean",
        "memory_checker": "valgrind --leak-check=full --error-exitcode=1",
    }

    DEFAULT_JAVA_RULES: Dict[str, Any] = {
        "compiler": "javac",
        "flags": ["-Xlint:all"],
        "runner": "java",
        "build_tool": "javac",
    }

    DEFAULT_PYTHON_RULES: Dict[str, Any] = {
        "runner": "pytest",
        "test_tool": "pytest",
        "command": [sys.executable, "-m", "pytest", "-v"],
        "default_language": "python",
    }

    def __init__(
        self,
        syllabus_detector: Optional[Any] = None,
        default_timeout: float = 30.0,
    ) -> None:
        self.syllabus_detector = syllabus_detector
        if self.syllabus_detector is None and SyllabusDetector is not None:
            try:
                self.syllabus_detector = SyllabusDetector()
            except Exception:
                self.syllabus_detector = None
        self.default_timeout = default_timeout

    def _get_execution_env(self) -> Dict[str, str]:
        """Constructs an environment with POSIX utilities available on Windows."""
        env = os.environ.copy()
        if sys.platform == "win32":
            additional_paths: List[str] = []
            git_usr_bin = Path(r"C:\Program Files\Git\usr\bin")
            mingw_bin = Path(r"C:\mingw64\bin")
            if git_usr_bin.exists():
                additional_paths.append(str(git_usr_bin))
            if mingw_bin.exists():
                additional_paths.append(str(mingw_bin))
            if additional_paths:
                env["PATH"] = os.pathsep.join(additional_paths) + os.pathsep + env.get("PATH", "")
        return env

    def _find_make_cmd(self, env: Optional[Dict[str, str]] = None) -> str:
        """Finds make or mingw32-make executable."""
        path = env.get("PATH") if env else None
        cmd = shutil.which("make", path=path) or shutil.which("mingw32-make", path=path)
        return cmd if cmd else "make"

    def has_valgrind(self, env: Optional[Dict[str, str]] = None) -> bool:
        """Checks if valgrind executable is available in PATH."""
        path = env.get("PATH") if env else None
        return shutil.which("valgrind", path=path) is not None

    def _resolve_compilation_rules(self, matiere_id: Optional[str]) -> Dict[str, Any]:
        """Resolves compilation flags and tools for the course subject."""
        if matiere_id and self.syllabus_detector:
            try:
                info = self.syllabus_detector.get_matiere(matiere_id)
                if info.compilation_rules:
                    return info.compilation_rules
            except Exception:
                pass

        if matiere_id in ["python", "python_data", "ia_ml"]:
            return self.DEFAULT_PYTHON_RULES
        if matiere_id == "java_poo":
            return self.DEFAULT_JAVA_RULES
        return self.DEFAULT_C_RULES

    def _find_source_files(self, proj_path: Path, ext: str) -> List[Path]:
        """Finds source files in project root and subdirectories (e.g. src/), excluding hidden/venv dirs."""
        files: List[Path] = []
        ignored_dirs = {".git", ".pytest_cache", "__pycache__", ".venv", "venv", "env", ".tox", "build", "dist"}
        for p in proj_path.rglob(f"*.{ext}"):
            if not any(part in ignored_dirs for part in p.parts):
                files.append(p)
        return sorted(files)

    def _parse_diagnostics(self, output: str) -> tuple[int, int]:
        """Parses warnings and errors count from compiler and pytest output."""
        warnings_count = 0
        errors_count = 0

        summary_patterns = [
            re.compile(r"all warnings being treated as errors", re.IGNORECASE),
            re.compile(r"make(\[\d+\])?:\s*\*\*\*", re.IGNORECASE),
        ]

        # Pytest summary extraction
        pytest_failed_m = re.findall(r"(?:^|\s)(\d+)\s+failed", output, re.IGNORECASE)
        pytest_errors_m = re.findall(r"(?:^|\s)(\d+)\s+errors?", output, re.IGNORECASE)
        pytest_warnings_m = re.findall(r"(?:^|\s)(\d+)\s+warnings?", output, re.IGNORECASE)

        if pytest_failed_m:
            errors_count += sum(int(x) for x in pytest_failed_m)
        if pytest_errors_m:
            errors_count += sum(int(x) for x in pytest_errors_m)
        if pytest_warnings_m:
            warnings_count += sum(int(x) for x in pytest_warnings_m)

        for line in output.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            if any(p.search(line_str) for p in summary_patterns):
                continue

            # Skip pytest summary delimiter line
            if re.search(r"==+.*(?:passed|failed|warnings?).*==+", line_str):
                continue

            # Warning detection (C, Java, Python)
            is_warning = False
            if re.search(r"\[-W[a-zA-Z0-9_-]+\]", line_str) or re.search(r"\[-Werror", line_str):
                is_warning = True
            elif re.search(r"(?:^|[\s:])warning:\s+", line_str, re.IGNORECASE):
                is_warning = True
            elif re.search(r"(?:UserWarning|DeprecationWarning|PytestWarning):", line_str):
                if not pytest_warnings_m:
                    is_warning = True

            # Error detection
            is_error = False
            if re.search(r"(?:^|[\s:])(?:fatal\s+)?error:\s+", line_str, re.IGNORECASE):
                is_error = True
            elif re.search(r"^FAILED\s+[^\s]+", line_str):
                if not pytest_failed_m and not pytest_errors_m:
                    is_error = True
            elif re.search(r"(?:SyntaxError|IndentationError):", line_str):
                if not pytest_failed_m and not pytest_errors_m:
                    is_error = True

            if is_warning:
                warnings_count += 1
            if is_error:
                errors_count += 1

        return warnings_count, errors_count

    def _locate_binary(self, project_path: Path, preferred_name: Optional[str] = None) -> Optional[Path]:
        """Locates the executable binary, Java class, or Python script generated by or for the build."""
        candidates: List[Path] = []
        if preferred_name:
            candidates.extend([
                project_path / preferred_name,
                project_path / f"{preferred_name}.exe",
                project_path / f"{preferred_name}.class",
                project_path / f"{preferred_name}.py",
                project_path / "src" / f"{preferred_name}.py",
            ])

        # Common executable / entrypoint names
        for default_name in ["test_bin", "app", "calc", "demo", "main", "run", "artifact", "a.out"]:
            candidates.extend([
                project_path / default_name,
                project_path / f"{default_name}.exe",
                project_path / f"{default_name}.py",
                project_path / "src" / f"{default_name}.py",
            ])

        for c in candidates:
            if c.exists() and c.is_file():
                return c

        # Scan project dir for newly created .exe, .class, .py, or executable files
        all_executables: List[Path] = []
        for file in project_path.rglob("*"):
            if file.is_file():
                parts = set(file.parts)
                if any(p in parts for p in [".git", ".pytest_cache", "__pycache__", ".venv", "venv"]):
                    continue
                if file.suffix.lower() in [".exe", ".class"] or (os.access(str(file), os.X_OK) and file.suffix == ""):
                    all_executables.append(file)
                elif file.name in ["main.py", "app.py", "solution.py"]:
                    all_executables.append(file)

        if all_executables:
            all_executables.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return all_executables[0]

        return None

    def execute_binary(
        self,
        binary_path: Union[str, Path],
        args: Optional[List[str]] = None,
        stdin_data: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Executes a compiled binary, Java class, or Python script, capturing exact stdout, stderr, and exit code."""
        bin_path = Path(binary_path).resolve()
        if not bin_path.exists():
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Binary not found: {bin_path}",
                command=[str(bin_path)],
                duration_sec=0.0,
            )

        env = self._get_execution_env()
        exec_timeout = timeout if timeout is not None else 10.0

        if bin_path.suffix.lower() == ".class":
            java_bin = shutil.which("java", path=env.get("PATH")) or "java"
            cmd = [java_bin, "-cp", str(bin_path.parent), bin_path.stem] + (args or [])
        elif bin_path.suffix.lower() == ".py":
            py_bin = sys.executable or shutil.which("python", path=env.get("PATH")) or "python"
            cmd = [py_bin, str(bin_path)] + (args or [])
        else:
            cmd = [str(bin_path)] + (args or [])

        start_time = time.time()
        try:
            proc = subprocess.run(
                cmd,
                input=stdin_data,
                cwd=str(bin_path.parent),
                capture_output=True,
                text=True,
                timeout=exec_timeout,
                env=env,
            )
            duration = time.time() - start_time
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                command=cmd,
                duration_sec=duration,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start_time
            stdout_str = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode("utf-8", errors="replace") if exc.stdout else "")
            stderr_str = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode("utf-8", errors="replace") if exc.stderr else "")
            return ExecutionResult(
                exit_code=-1,
                stdout=stdout_str,
                stderr=(stderr_str + f"\n[Process killed: timed out after {exec_timeout}s]").strip(),
                command=cmd,
                duration_sec=duration,
            )
        except Exception as exc:
            duration = time.time() - start_time
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"Failed to execute binary: {exc}",
                command=cmd,
                duration_sec=duration,
            )

    def build_and_test(
        self,
        project_dir: Union[str, Path],
        matiere_id: Optional[str] = "langage_c",
        target: Optional[str] = "all",
        strict_warnings: bool = True,
        run_binary: bool = False,
        binary_name: Optional[str] = None,
        binary_args: Optional[List[str]] = None,
        binary_stdin: Optional[str] = None,
        run_valgrind: bool = False,
        timeout: Optional[float] = None,
    ) -> BuildResult:
        """Compiles the project and optionally runs binary and tests."""
        proj_path = Path(project_dir).resolve()
        if not proj_path.exists() or not proj_path.is_dir():
            return BuildResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Project directory does not exist: {project_dir}",
                warnings_count=0,
                errors_count=1,
                project_dir=str(project_dir),
            )

        timeout = timeout or self.default_timeout
        rules = self._resolve_compilation_rules(matiere_id)
        env = self._get_execution_env()

        # Check for Makefile
        makefile_path = None
        for mf_name in ["Makefile", "makefile", "GNUmakefile"]:
            candidate = proj_path / mf_name
            if candidate.exists():
                makefile_path = candidate
                break

        build_cmd: List[str] = []
        c_files = self._find_source_files(proj_path, "c")
        java_files = self._find_source_files(proj_path, "java")
        py_files = self._find_source_files(proj_path, "py")

        is_python_project = (
            matiere_id in ["python", "python_data", "ia_ml"]
            or (bool(py_files) and not c_files and not java_files and not makefile_path)
        )

        if makefile_path:
            make_bin = self._find_make_cmd(env)
            build_cmd = [make_bin]
            if target:
                build_cmd.append(target)
        elif is_python_project:
            py_bin = sys.executable or shutil.which("python", path=env.get("PATH")) or "python"
            has_test_files = any(
                p.name.startswith("test_") or p.name.endswith("_test.py") or "test" in p.parts
                for p in py_files
            )
            if has_test_files:
                build_cmd = [py_bin, "-m", "pytest", "-v"]
            elif py_files:
                build_cmd = [py_bin, "-m", "py_compile"] + [str(f.relative_to(proj_path)) for f in py_files]
            else:
                build_cmd = [py_bin, "-m", "pytest", "-v"]
        elif java_files:
            compiler = rules.get("compiler", "javac")
            flags = rules.get("flags", ["-Xlint:all"])
            build_cmd = [compiler] + flags + [str(f.relative_to(proj_path)) for f in java_files]
        elif c_files:
            compiler = rules.get("compiler", "gcc")
            flags = rules.get("flags", ["-Wall", "-Wextra", "-Werror", "-pedantic", "-std=c11"])
            out_name = binary_name or "test_bin"
            build_cmd = [compiler] + flags + ["-o", out_name] + [str(f.relative_to(proj_path)) for f in c_files]
        else:
            return BuildResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"No Makefile or source files (.c, .java, .py) found in {proj_path}",
                project_dir=str(proj_path),
            )

        try:
            proc = subprocess.run(
                build_cmd,
                cwd=str(proj_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            return BuildResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Build timed out after {timeout} seconds",
                command=build_cmd,
                project_dir=str(proj_path),
            )
        except Exception as exc:
            return BuildResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Failed to run build command: {exc}",
                command=build_cmd,
                project_dir=str(proj_path),
            )

        combined_diagnostics = stdout + "\n" + stderr
        warnings_count, errors_count = self._parse_diagnostics(combined_diagnostics)

        # Build success evaluation
        is_success = (exit_code == 0)
        if strict_warnings and warnings_count > 0:
            is_success = False

        # Detect generated artifacts
        artifacts: List[str] = []
        for ext in [".exe", ".o", ".class", ".pyc"]:
            artifacts.extend([f.name for f in proj_path.rglob(f"*{ext}")])
        for bin_candidate in ["test_bin", "app", "demo", "calc", "main", "artifact"]:
            if (proj_path / bin_candidate).exists():
                artifacts.append(bin_candidate)
        artifacts = sorted(list(set(artifacts)))

        result = BuildResult(
            success=is_success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            warnings_count=warnings_count,
            errors_count=errors_count,
            command=build_cmd,
            artifacts=artifacts,
            project_dir=str(proj_path),
        )

        # Optional binary execution step
        if is_success and run_binary:
            binary_file = self._locate_binary(proj_path, preferred_name=binary_name)
            if binary_file:
                exec_timeout = timeout if timeout is not None else 10.0
                exec_res = self.execute_binary(
                    binary_path=binary_file,
                    args=binary_args,
                    stdin_data=binary_stdin,
                    timeout=exec_timeout,
                )
                result.execution_result = exec_res
                if not exec_res.success:
                    result.success = False
            else:
                result.execution_result = ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr="Compiled binary could not be located in project directory.",
                )
                result.success = False

        # Optional Valgrind memory leak audit
        if is_success and run_valgrind:
            binary_file = self._locate_binary(proj_path, preferred_name=binary_name)
            if self.has_valgrind(env) and binary_file:
                valgrind_cmd = [
                    "valgrind",
                    "--leak-check=full",
                    "--show-leak-kinds=all",
                    "--error-exitcode=1",
                    str(binary_file),
                ]
                if binary_args:
                    valgrind_cmd.extend(binary_args)

                vg_timeout = timeout if timeout is not None else 15.0
                try:
                    vg_proc = subprocess.run(
                        valgrind_cmd,
                        input=binary_stdin,
                        cwd=str(proj_path),
                        capture_output=True,
                        text=True,
                        timeout=vg_timeout,
                        env=env,
                    )
                    result.valgrind_report = vg_proc.stderr or vg_proc.stdout
                    result.valgrind_clean = (vg_proc.returncode == 0)
                    if not result.valgrind_clean:
                        result.success = False
                except Exception as exc:
                    result.valgrind_clean = False
                    result.valgrind_report = f"Valgrind execution error: {exc}"
                    result.success = False
            else:
                result.valgrind_clean = None
                result.valgrind_report = (
                    "Valgrind not found on system (Windows/MinGW host). "
                    "Zero-leak memory audit skipped."
                )

        return result

    def clean(self, project_dir: Union[str, Path], target: str = "clean") -> BuildResult:
        """Cleans build artifacts using make clean or by removing generated binaries."""
        proj_path = Path(project_dir).resolve()
        if not proj_path.exists() or not proj_path.is_dir():
            return BuildResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Project directory does not exist: {project_dir}",
                project_dir=str(project_dir),
            )

        env = self._get_execution_env()
        makefile_path = None
        for mf_name in ["Makefile", "makefile", "GNUmakefile"]:
            candidate = proj_path / mf_name
            if candidate.exists():
                makefile_path = candidate
                break

        stdout = ""
        stderr = ""
        exit_code = 0
        cmd: List[str] = []

        if makefile_path:
            make_bin = self._find_make_cmd(env)
            cmd = [make_bin, target]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(proj_path),
                    capture_output=True,
                    text=True,
                    timeout=self.default_timeout,
                    env=env,
                )
                stdout = proc.stdout
                stderr = proc.stderr
                exit_code = proc.returncode
            except Exception as exc:
                stderr = f"Error running make clean: {exc}"
                exit_code = 1

        # Remove binaries, object files, class files, pyc files
        for pattern in ["*.o", "*.obj", "*.class", "*.exe", "*.pyc"]:
            for f in proj_path.rglob(pattern):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

        for bin_name in ["test_bin", "app", "demo", "calc", "main", "artifact", "run", "a.out"]:
            for f in [proj_path / bin_name, proj_path / f"{bin_name}.exe"]:
                if f.exists() and f.is_file():
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass

        for cache_name in ["__pycache__", ".pytest_cache"]:
            for d in proj_path.rglob(cache_name):
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)

        return BuildResult(
            success=(exit_code == 0),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            command=cmd,
            project_dir=str(proj_path),
        )
