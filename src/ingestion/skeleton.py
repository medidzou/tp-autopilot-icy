"""Skeleton code parser and function signature preservation validator for C and Java."""

from __future__ import annotations

import os
import re
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# C / C++ and Java keywords that cannot be function names
CONTROL_KEYWORDS: Set[str] = {
    "if", "else", "while", "for", "do", "switch", "case", "default",
    "return", "sizeof", "typedef", "struct", "union", "enum", "class",
    "interface", "catch", "try", "throw", "throws", "finally", "new",
    "delete", "goto", "break", "continue", "assert", "import", "package"
}

TYPE_KEYWORDS: Set[str] = {
    "int", "char", "short", "long", "float", "double", "void",
    "unsigned", "signed", "bool", "boolean", "byte", "size_t",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t", "int8_t", "int16_t",
    "int32_t", "int64_t", "ssize_t", "off_t", "pid_t", "mode_t",
    "String", "Object", "List", "Map", "Set"
}

STORAGE_MODIFIERS: Set[str] = {
    "static", "inline", "extern", "register", "volatile", "const",
    "public", "private", "protected", "abstract", "final", "native",
    "synchronized", "strictfp", "__inline__", "__attribute__"
}


def _normalize_type(type_str: str) -> str:
    """Normalizes a type string for comparison (handling pointer asterisks, arrays, whitespace)."""
    t = type_str.strip()
    # Normalize multiple whitespaces
    t = re.sub(r"\s+", " ", t)
    # Strip all whitespace around asterisks: "char * *" -> "char**"
    t = re.sub(r"\s*\*\s*", "*", t)
    # Ensure a single space before asterisks if preceded by a word or bracket char: "char**" -> "char **"
    t = re.sub(r"([a-zA-Z0-9_>\]])\*", r"\1 *", t)
    # Normalize array brackets: "int []" -> "int[]"
    t = re.sub(r"\s*\[\s*\]", "[]", t)
    return t.strip()


def _normalize_param_type(param_str: str) -> Tuple[str, str]:
    """Splits a single parameter declaration into (normalized_type, param_name).

    Examples:
        'const char *buffer' -> ('const char *', 'buffer')
        'size_t len' -> ('size_t', 'len')
        'int *arr[]' -> ('int *[]', 'arr')
        'const char *' -> ('const char *', '')
        'int' -> ('int', '')
        'void' -> ('void', '')
    """
    param_str = param_str.strip()
    if not param_str or param_str == "void":
        return ("void", "")

    # Match trailing parameter name if present
    # Case: name with optional array brackets, e.g. "buffer", "arr[]", "matrix[][]"
    match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)(\s*\[\s*\])*$", param_str)
    if match:
        name = match.group(1)
        brackets = match.group(2) or ""
        type_part = param_str[: match.start(1)].strip()
        if brackets:
            brackets = re.sub(r"\s*", "", brackets)

        # If type_part is empty, check if the single word is a type or a name without type
        if not type_part:
            # Single word like "size_t" or "int" is the type, not the name
            return (_normalize_type(name + brackets), "")

        # If type_part ends with struct/union/enum without '*', name is the tag of compound type
        # E.g. "struct point" -> type is "struct point", param name is ""
        last_type_word = type_part.split()[-1] if type_part.split() else ""
        if last_type_word in ("struct", "union", "enum") and not type_part.endswith("*"):
            full_type = f"{type_part} {name}{brackets}"
            return (_normalize_type(full_type), "")

        # If name is itself a type keyword and there is another type qualifier (e.g. "unsigned int")
        if name in TYPE_KEYWORDS and not type_part.endswith("*"):
            full_type = f"{type_part} {name}{brackets}"
            return (_normalize_type(full_type), "")

        if brackets:
            type_part = f"{type_part} {brackets}" if type_part else brackets

        return (_normalize_type(type_part), name)

    # No trailing identifier found (e.g. "const char *", "int *")
    return (_normalize_type(param_str), "")


@dataclass
class TodoSlot:
    """Represents a TODO comment location in a skeleton code file."""

    file_path: str
    line_number: int
    todo_text: str
    function_name: Optional[str] = None
    signature: Optional[str] = None
    language: str = "c"


@dataclass
class FunctionSignature:
    """Represents an extracted function or method prototype/definition."""

    name: str
    return_type: str
    parameters: List[str] = field(default_factory=list)
    param_types: List[str] = field(default_factory=list)
    file_path: str = ""
    line_number: int = 1
    is_declaration: bool = False
    language: str = "c"
    raw_signature: str = ""
    is_static: bool = False
    modifiers: List[str] = field(default_factory=list)

    def matches(self, other: FunctionSignature, strict_param_names: bool = False) -> bool:
        """Checks if another signature conforms to this signature."""
        if self.name != other.name:
            return False

        if _normalize_type(self.return_type) != _normalize_type(other.return_type):
            return False

        # Compare parameters
        self_types = [p for p in self.param_types if p != "void"]
        other_types = [p for p in other.param_types if p != "void"]

        if len(self_types) != len(other_types):
            return False

        for st, ot in zip(self_types, other_types):
            if _normalize_type(st) != _normalize_type(ot):
                return False

        if strict_param_names:
            if len(self.parameters) != len(other.parameters):
                return False
            for sp, op in zip(self.parameters, other.parameters):
                _, s_name = _normalize_param_type(sp)
                _, o_name = _normalize_param_type(op)
                if s_name and o_name and s_name != o_name:
                    return False

        return True


class SkeletonProject:
    """Encapsulates a parsed skeleton project with files, TODO slots, and function signatures."""

    def __init__(
        self,
        files: Dict[str, str],
        todo_slots: List[TodoSlot],
        signatures: Dict[str, List[FunctionSignature]],
    ) -> None:
        self._files = dict(files)
        self._todo_slots = list(todo_slots)
        self._signatures = dict(signatures)
        # Fast lookup by function name across all files
        self._signatures_by_name: Dict[str, List[FunctionSignature]] = {}
        for file_sigs in self._signatures.values():
            for sig in file_sigs:
                self._signatures_by_name.setdefault(sig.name, []).append(sig)

    @property
    def files(self) -> Dict[str, str]:
        """Dictionary of relative file paths to their content."""
        return self._files

    @property
    def todo_slots(self) -> List[TodoSlot]:
        """List of all TODO slots found in the skeleton."""
        return self._todo_slots

    @property
    def signatures(self) -> Dict[str, List[FunctionSignature]]:
        """Signatures grouped by relative file path."""
        return self._signatures

    def get_todo_locations(self) -> List[TodoSlot]:
        """Returns all TODO slots in the skeleton project."""
        return list(self._todo_slots)

    def get_file(self, file_path: str) -> Optional[str]:
        """Retrieves raw content of a file in the skeleton project."""
        # Normalize slashes
        norm_path = file_path.replace("\\", "/")
        for path, content in self._files.items():
            if path.replace("\\", "/") == norm_path:
                return content
        return None

    def list_files(self) -> List[str]:
        """Returns list of relative file paths in the skeleton."""
        return list(self._files.keys())

    def get_function_signatures(self, file_path: Optional[str] = None) -> List[FunctionSignature]:
        """Returns function signatures, optionally filtered by file path."""
        if file_path is None:
            all_sigs: List[FunctionSignature] = []
            for sigs in self._signatures.values():
                all_sigs.extend(sigs)
            return all_sigs

        norm_path = file_path.replace("\\", "/")
        for path, sigs in self._signatures.items():
            if path.replace("\\", "/") == norm_path:
                return list(sigs)
        return []

    def validate_signatures_preserved(
        self, modified_files: Dict[str, str], strict_param_names: bool = False
    ) -> bool:
        """Validates that all skeleton function prototypes are preserved verbatim in modified files.

        Returns:
            True if all original functions in the modified files exist and preserve their
            return type and parameter signatures. Extra helper functions added in modified files
            are permitted. Returns False if any original function is missing or altered.
        """
        parser = SkeletonParser()

        # Parse modified files
        modified_project = parser.parse_files(modified_files)
        all_new_sigs = modified_project.get_function_signatures()

        # 1. Per-file exact match check (when filenames match directly)
        checked_orig_sigs: Set[Tuple[str, str, int]] = set()

        for mod_path, _ in modified_files.items():
            norm_mod_path = mod_path.replace("\\", "/")

            # Find matching original file signatures
            orig_sigs: List[FunctionSignature] = []
            for orig_path, sigs in self._signatures.items():
                if orig_path.replace("\\", "/") == norm_mod_path:
                    orig_sigs = sigs
                    break

            if not orig_sigs:
                continue

            # Modified file signatures
            new_sigs = modified_project.get_function_signatures(norm_mod_path)

            # Check that every original function exists with matching signature
            for orig_sig in orig_sigs:
                has_match = any(
                    orig_sig.matches(cand, strict_param_names=strict_param_names)
                    for cand in new_sigs
                    if cand.name == orig_sig.name
                )
                if not has_match:
                    return False
                checked_orig_sigs.add((orig_sig.file_path, orig_sig.name, orig_sig.line_number))

        # 2. Global cross-file invariant check:
        # Every function signature in the skeleton (including headers like .h and subject_prototypes.h)
        # must be preserved either in the corresponding file OR across the implementation files.
        for orig_sig in self.get_function_signatures():
            sig_key = (orig_sig.file_path, orig_sig.name, orig_sig.line_number)
            if sig_key in checked_orig_sigs:
                continue

            has_global_match = any(
                orig_sig.matches(cand, strict_param_names=strict_param_names)
                for cand in all_new_sigs
                if cand.name == orig_sig.name
            )
            if not has_global_match:
                return False

        return True

    def validate_signatures(
        self, modified_files: Dict[str, str], strict_param_names: bool = False
    ) -> bool:
        """Alias for validate_signatures_preserved."""
        return self.validate_signatures_preserved(modified_files, strict_param_names=strict_param_names)


class SkeletonParser:
    """Parses skeleton code archives or files, detects TODOs, and extracts function signatures."""

    TODO_PATTERN = re.compile(r"\b(todo|fixme|a[-_ ]faire|à[-_ ]faire|xxx)\b", re.IGNORECASE)

    def extract_skeleton(self, zip_path: str | Path) -> SkeletonProject:
        """Extracts and parses a skeleton project from a .zip, .tar, or folder path.

        Raises:
            FileNotFoundError: If the archive path does not exist.
        """
        path = Path(zip_path)
        if not path.exists():
            raise FileNotFoundError(f"Skeleton file or directory not found: {zip_path}")

        if path.is_dir():
            return self.parse_directory(path)

        files: Dict[str, str] = {}

        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    # Skip OS-specific hidden metadata
                    filename = member.filename.replace("\\", "/")
                    if filename.startswith("__MACOSX/") or filename.endswith(".DS_Store"):
                        continue
                    # Zip-Slip defense: prevent path traversal or absolute escape
                    p = Path(filename)
                    if p.is_absolute() or bool(p.root) or ".." in p.parts:
                        continue
                    try:
                        raw = zf.read(member)
                        files[filename] = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        files[filename] = raw.decode("latin-1", errors="replace")
            return self.parse_files(files)

        if tarfile.is_tarfile(path):
            with tarfile.open(path, "r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    filename = member.name.replace("\\", "/")
                    if filename.startswith("__MACOSX/") or filename.endswith(".DS_Store"):
                        continue
                    # Zip-Slip defense: prevent path traversal or absolute escape
                    p = Path(filename)
                    if p.is_absolute() or bool(p.root) or ".." in p.parts:
                        continue
                    f = tf.extractfile(member)
                    if f is not None:
                        raw = f.read()
                        try:
                            files[filename] = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            files[filename] = raw.decode("latin-1", errors="replace")
            return self.parse_files(files)

        raise ValueError(f"Unsupported skeleton archive format: {zip_path}")

    def parse_directory(self, dir_path: str | Path) -> SkeletonProject:
        """Parses all code files within a directory as a SkeletonProject."""
        root = Path(dir_path)
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_path}")

        files: Dict[str, str] = {}
        for path in root.rglob("*"):
            if path.is_file():
                rel_path = str(path.relative_to(root)).replace("\\", "/")
                if any(part.startswith(".") for part in path.parts):
                    continue
                try:
                    files[rel_path] = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    files[rel_path] = path.read_text(encoding="latin-1", errors="replace")

        return self.parse_files(files)

    def parse_files(self, files: Dict[str, str]) -> SkeletonProject:
        """Parses an in-memory dictionary of relative file paths and content."""
        all_todo_slots: List[TodoSlot] = []
        all_signatures: Dict[str, List[FunctionSignature]] = {}

        for file_path, content in files.items():
            lang = self._detect_language(file_path)
            todos, sigs = self._scan_source(file_path, content, lang)
            all_todo_slots.extend(todos)
            all_signatures[file_path] = sigs

        return SkeletonProject(files=files, todo_slots=all_todo_slots, signatures=all_signatures)

    @classmethod
    def verify_invariants(
        cls,
        skeleton: Union[SkeletonProject, Dict[str, str], str, Path],
        modified_files: Dict[str, str],
        strict_param_names: bool = False,
    ) -> bool:
        """Verifies that all function prototypes and signatures from the skeleton are preserved verbatim."""
        parser = cls()
        if isinstance(skeleton, SkeletonProject):
            project = skeleton
        elif isinstance(skeleton, dict):
            project = parser.parse_files(skeleton)
        elif isinstance(skeleton, (str, Path)):
            project = parser.extract_skeleton(skeleton)
        else:
            raise TypeError(f"Unsupported skeleton type: {type(skeleton)}")

        return project.validate_signatures_preserved(
            modified_files=modified_files,
            strict_param_names=strict_param_names,
        )

    def _detect_language(self, file_path: str) -> str:
        """Detects the source programming language based on file extension."""
        lower = file_path.lower()
        if lower.endswith((".c", ".h", ".cpp", ".hpp", ".cc")):
            return "c"
        if lower.endswith(".java"):
            return "java"
        if lower.endswith(".py"):
            return "python"
        return "c"

    def _parse_signature_header(
        self, header: str, file_path: str, line_num: int, is_declaration: bool, lang: str
    ) -> Optional[FunctionSignature]:
        """Extracts FunctionSignature from a prototype or function definition header string."""
        # Remove trailing throws or qualifiers
        header = header.strip()
        # Clean newlines and consecutive whitespace
        clean_header = re.sub(r"\s+", " ", header)

        # Match balanced parens for parameters
        last_paren_close = clean_header.rfind(")")
        if last_paren_close == -1:
            return None

        # Find matching '(' from the back
        depth = 0
        open_paren_idx = -1
        for idx in range(last_paren_close, -1, -1):
            if clean_header[idx] == ")":
                depth += 1
            elif clean_header[idx] == "(":
                depth -= 1
                if depth == 0:
                    open_paren_idx = idx
                    break

        if open_paren_idx == -1:
            return None

        param_content = clean_header[open_paren_idx + 1 : last_paren_close].strip()
        prefix = clean_header[:open_paren_idx].strip()

        # Find function name: last identifier in prefix
        name_match = re.search(r"([a-zA-Z_][a-zA-Z0-9_]*)$", prefix)
        if not name_match:
            return None

        func_name = name_match.group(1)
        if func_name in CONTROL_KEYWORDS:
            return None

        # Everything before the function name is return type & modifiers
        ret_prefix = prefix[: name_match.start(1)].strip()
        if not ret_prefix:
            # Possible constructor or invalid
            return None

        # Check for assignment '=' which indicates a variable initialization
        if "=" in ret_prefix:
            return None

        # Extract modifiers
        modifiers: List[str] = []
        words = ret_prefix.split()
        clean_ret_words: List[str] = []
        is_static = False
        for w in words:
            if w in ("static", "inline", "public", "private", "protected", "abstract", "final", "extern"):
                modifiers.append(w)
                if w == "static":
                    is_static = True
            else:
                clean_ret_words.append(w)

        return_type = " ".join(clean_ret_words).strip()
        if not return_type:
            return None

        # Parse parameters
        params: List[str] = []
        param_types: List[str] = []
        if param_content and param_content != "void":
            raw_params = [p.strip() for p in param_content.split(",") if p.strip()]
            for p in raw_params:
                p_type, _ = _normalize_param_type(p)
                if p_type and p_type != "void":
                    params.append(p)
                    param_types.append(p_type)

        return FunctionSignature(
            name=func_name,
            return_type=_normalize_type(return_type),
            parameters=params,
            param_types=param_types,
            file_path=file_path,
            line_number=line_num,
            is_declaration=is_declaration,
            language=lang,
            raw_signature=clean_header,
            is_static=is_static,
            modifiers=modifiers,
        )

    def _scan_source(
        self, file_path: str, content: str, lang: str
    ) -> Tuple[List[TodoSlot], List[FunctionSignature]]:
        """Scans C or Java source code extracting TODO comments and function signatures."""
        todos: List[TodoSlot] = []
        signatures: List[FunctionSignature] = []

        # Scope stack: list of (FunctionSignature, brace_depth)
        scope_stack: List[Tuple[FunctionSignature, int]] = []

        lines = content.splitlines(keepends=True)
        in_block_comment = False
        block_comment_text = ""
        block_comment_start_line = 1

        brace_depth = 0
        statement_buffer: List[str] = []
        statement_start_line = 1

        for line_idx, line in enumerate(lines, start=1):
            i = 0
            n = len(line)

            # Skip preprocessor lines in C at line start
            stripped = line.strip()
            if not in_block_comment and stripped.startswith("#"):
                # Still check if preprocessor line contains a TODO
                if self.TODO_PATTERN.search(stripped):
                    current_func = scope_stack[-1][0].name if scope_stack else None
                    todos.append(
                        TodoSlot(
                            file_path=file_path,
                            line_number=line_idx,
                            todo_text=stripped,
                            function_name=current_func,
                            language=lang,
                        )
                    )
                continue

            while i < n:
                if in_block_comment:
                    if line[i : i + 2] == "*/":
                        block_comment_text += "*/"
                        in_block_comment = False
                        i += 2
                        if self.TODO_PATTERN.search(block_comment_text):
                            current_func = scope_stack[-1][0].name if scope_stack else None
                            todos.append(
                                TodoSlot(
                                    file_path=file_path,
                                    line_number=block_comment_start_line,
                                    todo_text=block_comment_text.strip(),
                                    function_name=current_func,
                                    language=lang,
                                )
                            )
                        block_comment_text = ""
                    else:
                        block_comment_text += line[i]
                        i += 1
                    continue

                # Check block comment start
                if line[i : i + 2] == "/*":
                    in_block_comment = True
                    block_comment_text = "/*"
                    block_comment_start_line = line_idx
                    i += 2
                    continue

                # Check line comment start
                if line[i : i + 2] == "//":
                    line_comment = line[i:].rstrip("\r\n")
                    if self.TODO_PATTERN.search(line_comment):
                        current_func = scope_stack[-1][0].name if scope_stack else None
                        todos.append(
                            TodoSlot(
                                file_path=file_path,
                                line_number=line_idx,
                                todo_text=line_comment.strip(),
                                function_name=current_func,
                                language=lang,
                            )
                        )
                    break  # Rest of line is comment

                # Check string literal
                if line[i] == '"':
                    # Skip string literal
                    i += 1
                    while i < n and line[i] != '"':
                        if line[i] == "\\" and i + 1 < n:
                            i += 2
                        else:
                            i += 1
                    i += 1
                    continue

                # Check char literal
                if line[i] == "'":
                    i += 1
                    while i < n and line[i] != "'":
                        if line[i] == "\\" and i + 1 < n:
                            i += 2
                        else:
                            i += 1
                    i += 1
                    continue

                ch = line[i]

                if ch == "{":
                    header = "".join(statement_buffer).strip()
                    statement_buffer = []
                    brace_depth += 1

                    # In C: functions are defined at top-level (brace_depth == 1)
                    # In Java: methods are defined at class level (brace_depth == 2)
                    target_depth = 2 if lang == "java" else 1
                    if brace_depth == target_depth and "(" in header and ")" in header:
                        sig = self._parse_signature_header(
                            header,
                            file_path=file_path,
                            line_num=statement_start_line,
                            is_declaration=False,
                            lang=lang,
                        )
                        if sig:
                            signatures.append(sig)
                            scope_stack.append((sig, brace_depth))

                    i += 1
                    statement_start_line = line_idx
                    continue

                if ch == "}":
                    statement_buffer = []
                    if scope_stack and scope_stack[-1][1] == brace_depth:
                        scope_stack.pop()
                    brace_depth = max(0, brace_depth - 1)
                    i += 1
                    statement_start_line = line_idx
                    continue

                if ch == ";":
                    statement = "".join(statement_buffer).strip()
                    statement_buffer = []

                    # In C: declarations occur at top level (brace_depth == 0)
                    # In Java: abstract methods or interface declarations occur at brace_depth == 1
                    target_decl_depth = 1 if lang == "java" else 0
                    if brace_depth == target_decl_depth and "(" in statement and ")" in statement:
                        sig = self._parse_signature_header(
                            statement,
                            file_path=file_path,
                            line_num=statement_start_line,
                            is_declaration=True,
                            lang=lang,
                        )
                        if sig:
                            signatures.append(sig)

                    i += 1
                    statement_start_line = line_idx
                    continue

                if not statement_buffer:
                    statement_start_line = line_idx
                statement_buffer.append(ch)
                i += 1

        return todos, signatures
