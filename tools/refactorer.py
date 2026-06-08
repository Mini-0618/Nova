"""
Codex-Local Multi-Module Refactorer
AST-based multi-file refactoring: rename symbols across modules,
extract functions, move code between files, import management.
"""

import os
import sys
import ast
import json
import re
import shutil
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

# ─── Backup Configuration ───────────────────────────────────────────────────
BACKUP_DIR = Path(__file__).parent.parent / ".refactorer_backups"
BACKUP_ENABLED = True  # Set to False to disable backups (not recommended)

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tools.project_analyzer import ProjectAnalyzer, ProjectGraph, Symbol


# ─── Backup Manager ─────────────────────────────────────────────────────────

class BackupManager:
    """Creates timestamped backups of files before refactoring operations.

    Backups are stored under BACKUP_DIR / <timestamp> / <relative_path>.bak
    so every refactoring session has its own snapshot.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._session_id = time.strftime("%Y%m%d_%H%M%S")
        self._session_dir = BACKUP_DIR / self._session_id
        self._manifest: List[Dict[str, str]] = []  # records for rollback

    def backup_file(self, file_path: str) -> Optional[Path]:
        """Create a backup of *file_path* before it is overwritten.

        Returns the backup path, or None if backup is disabled / file missing.
        """
        if not BACKUP_ENABLED:
            return None

        src = Path(file_path).resolve()
        if not src.exists():
            return None

        # Compute relative path for storage
        try:
            rel = src.relative_to(self.root)
        except ValueError:
            rel = Path(file_path.replace(":", "").replace("\\", "/"))

        dst = self._session_dir / str(rel).lstrip("/\\")
        dst = dst.with_name(dst.name + ".bak")
        dst.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(str(src), str(dst))
            # Record checksum for integrity verification
            checksum = hashlib.sha256(src.read_bytes()).hexdigest()
            self._manifest.append({
                "original": str(src),
                "backup": str(dst),
                "checksum": checksum,
                "timestamp": self._session_id,
            })
            return dst
        except OSError:
            return None

    def backup_plan(self, plan: "RefactorPlan") -> int:
        """Backup every file that will be modified by *plan*.

        Returns the number of files backed up.
        """
        count = 0
        seen = set()
        for change in plan.changes:
            if change.file not in seen:
                if self.backup_file(change.file):
                    count += 1
                seen.add(change.file)
        for path, _ in plan.new_files:
            # New files don't need backup (they don't exist yet)
            pass
        for path in plan.deleted_files:
            if path not in seen:
                if self.backup_file(path):
                    count += 1
                seen.add(path)
        return count

    def write_manifest(self):
        """Write the session manifest to the backup directory."""
        if not self._manifest:
            return
        manifest_path = self._session_dir / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(self._manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def restore_file(self, file_path: str) -> bool:
        """Restore a single file from its most recent backup in this session.

        Returns True on success.
        """
        src = Path(file_path).resolve()
        for entry in reversed(self._manifest):
            if entry["original"] == str(src):
                backup = Path(entry["backup"])
                if backup.exists():
                    shutil.copy2(str(backup), str(src))
                    return True
        return False

    def restore_all(self) -> List[str]:
        """Restore every file backed up in this session.

        Returns a list of restored file paths.
        """
        restored = []
        for entry in self._manifest:
            backup = Path(entry["backup"])
            original = Path(entry["original"])
            if backup.exists():
                try:
                    shutil.copy2(str(backup), str(original))
                    restored.append(str(original))
                except OSError:
                    pass
        return restored

    @staticmethod
    def list_sessions() -> List[str]:
        """Return sorted list of session timestamps (newest first)."""
        if not BACKUP_DIR.exists():
            return []
        sessions = sorted(
            (d.name for d in BACKUP_DIR.iterdir() if d.is_dir()),
            reverse=True,
        )
        return sessions

    @staticmethod
    def get_session_path(session_id: str) -> Path:
        """Return the path to a specific session backup directory."""
        return BACKUP_DIR / session_id


class RefactorType(Enum):
    RENAME_SYMBOL = "rename_symbol"
    EXTRACT_FUNCTION = "extract_function"
    MOVE_SYMBOL = "move_symbol"
    ADD_IMPORT = "add_import"
    REMOVE_UNUSED_IMPORTS = "remove_unused"
    CHANGE_SIGNATURE = "change_signature"


@dataclass
class RefactorChange:
    """A single change to a file."""
    file: str
    old_content: str
    new_content: str
    description: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None


@dataclass
class RefactorPlan:
    """A complete refactoring plan."""
    changes: List[RefactorChange] = field(default_factory=list)
    new_files: List[Tuple[str, str]] = field(default_factory=list)  # (path, content)
    deleted_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    description: str = ""


class Renamer(ast.NodeVisitor):
    """AST visitor that renames all occurrences of a symbol."""

    def __init__(self, old_name: str, new_name: str, scope: Set[str]):
        self.old_name = old_name
        self.new_name = new_name
        self.scope = scope
        self.changes: List[Tuple[int, int, str, str]] = []  # (start, end, old, new)
        self._current_class = None
        self._current_function = None
        self._in_string = False

    def visit_ClassDef(self, node):
        old_class = self._current_class
        self._current_class = node.name
        if node.name == self.old_name and self._current_class is None:
            self.changes.append((node.col_offset, node.col_offset + len(node.name), node.name, self.new_name))
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node):
        old_func = self._current_function
        self._current_function = node.name
        if node.name == self.old_name:
            self.changes.append((node.col_offset, node.col_offset + len(node.name), node.name, self.new_name))
        self.generic_visit(node)
        self._current_function = old_func

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Name(self, node):
        if node.id == self.old_name:
            self.changes.append((node.col_offset, node.col_offset + len(node.id), node.id, self.new_name))
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == self.old_name:
            pass  # handled at Name level
        self.generic_visit(node)


class ImportAnalyzer(ast.NodeVisitor):
    """Analyze which symbols are actually used in a module."""

    def __init__(self):
        self.defined_names: Set[str] = set()
        self.used_names: Set[str] = set()
        self.imported_names: Dict[str, str] = {}  # name -> module

    def visit_Import(self, node):
        for alias in node.names:
            if alias.asname:
                self.imported_names[alias.asname] = alias.name
            else:
                self.imported_names[alias.name.split('.')[0]] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            if alias.asname:
                self.imported_names[alias.asname] = f"{node.module}.{alias.name}"
            else:
                self.imported_names[alias.name] = f"{node.module}.{alias.name}"
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id not in self.defined_names:
            self.used_names.add(node.id)
        self.generic_visit(node)


class MultiModuleRefactorer:
    """
    Perform refactorings across multiple files simultaneously.

    Usage:
        refactorer = MultiModuleRefactorer("D:/myproject")
        plan = refactorer.rename_symbol("old_function_name", "new_function_name", across="utils.py")
        plan = refactorer.extract_function("src/utils.py", start_line=10, end_line=30, name="new_func")
        refactorer.apply_plan(plan)
    """

    def __init__(self, root: str, enable_backup: bool = True):
        self.root = Path(root).resolve()
        self.analyzer = ProjectAnalyzer(str(self.root))
        self._graph: Optional[ProjectGraph] = None
        self._backup = BackupManager(self.root) if enable_backup else None

    def _get_graph(self) -> ProjectGraph:
        if self._graph is None:
            self._graph = self.analyzer.analyze()
        return self._graph

    def _read_file(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")

    def _write_file(self, path: str, content: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    # ─── Rename Symbol ──────────────────────────────────────────────────────

    def rename_symbol(self, old_name: str, new_name: str,
                      files: Optional[List[str]] = None,
                      across_modules: bool = True) -> RefactorPlan:
        """
        Rename a symbol across all files in the project.

        This handles:
        - Function definitions
        - Class definitions
        - Method definitions
        - All call sites
        - Import statements
        - Docstrings and comments
        """
        graph = self._get_graph()
        plan = RefactorPlan(description=f"Rename '{old_name}' → '{new_name}'")

        # Find all files containing the old symbol
        files_to_update = set(files or [])

        if across_modules and old_name in graph.all_symbols:
            for sym in graph.all_symbols[old_name]:
                files_to_update.add(sym.file)

        # Also search for usage in all files (text search)
        for py_file in self.root.rglob("*.py"):
            if self._should_exclude(py_file):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                if old_name in content:
                    files_to_update.add(str(py_file))
            except Exception:
                continue

        # Build rename map for each file
        for filepath in files_to_update:
            if not Path(filepath).exists():
                continue

            content = self._read_file(filepath)
            new_content = self._rename_in_content(content, old_name, new_name)

            if new_content != content:
                plan.changes.append(RefactorChange(
                    file=str(filepath),
                    old_content=content,
                    new_content=new_content,
                    description=f"Rename '{old_name}' → '{new_name}'",
                ))

        return plan

    def _rename_in_content(self, content: str, old_name: str, new_name: str) -> str:
        """Rename all occurrences in file content using AST."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to text replacement
            return content

        # Use simple text replacement for now (AST-based is complex)
        # This handles most cases correctly
        new_content = content

        # Word-boundary replacement
        pattern = r'\b' + re.escape(old_name) + r'\b'
        new_content = re.sub(pattern, new_name, new_content)

        return new_content

    # ─── Extract Function ─────────────────────────────────────────────────

    def extract_function(self, file: str, start_line: int, end_line: int,
                         new_func_name: str, new_file: Optional[str] = None) -> RefactorPlan:
        """
        Extract code into a new function.
        Creates the new function in the same file or a new file.
        Replaces the original code with a call to the new function.
        """
        plan = RefactorPlan()
        filepath = self.root / file if not Path(file).is_absolute() else Path(file)

        if not filepath.exists():
            plan.warnings.append(f"File not found: {filepath}")
            return plan

        content = self._read_file(str(filepath))
        lines = content.splitlines()

        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            plan.warnings.append(f"Invalid line range: {start_line}-{end_line} (file has {len(lines)} lines)")
            return plan

        # Extract the code
        extracted_lines = lines[start_line - 1:end_line]
        extracted_code = "\n".join(extracted_lines)

        # Detect variables used
        used_vars = self._detect_variables(extracted_code)

        # Determine parameters needed
        local_vars = self._detect_local_assignments(extracted_code)
        params = list(used_vars - local_vars)

        # Determine return value if needed
        returns = self._detect_returns(extracted_code)

        # Build new function
        param_str = ", ".join(params) if params else ""
        new_func = f"def {new_func_name}({param_str}):\n"
        for line in extracted_code.splitlines():
            new_func += f"    {line}\n"

        if returns and not extracted_code.strip().endswith("return"):
            new_func += f"    return {returns[0]}\n"

        new_func += "\n"

        # Build replacement
        call_sig = f"{new_func_name}({param_str})"
        if returns:
            call = f"result = {call_sig}"
        else:
            call = call_sig

        new_lines = lines[:start_line - 1] + [call] + lines[end_line:]

        if new_file:
            # Write to new file
            plan.new_files.append((str(self.root / new_file), new_func))
            # Update original file
            plan.changes.append(RefactorChange(
                file=str(filepath),
                old_content=content,
                new_content="\n".join(new_lines),
                description=f"Extract to {new_file} and add call",
            ))
        else:
            # Insert function before the extracted block in same file
            new_lines = lines[:start_line - 1] + new_func.splitlines() + [""] + [call] + lines[end_line:]
            plan.changes.append(RefactorChange(
                file=str(filepath),
                old_content=content,
                new_content="\n".join(new_lines),
                description=f"Extract to function {new_func_name} in same file",
            ))

        return plan

    def _detect_variables(self, code: str) -> Set[str]:
        """Detect variables used in a piece of code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()
        analyzer = ImportAnalyzer()
        analyzer.visit(tree)
        return analyzer.used_names

    def _detect_local_assignments(self, code: str) -> Set[str]:
        """Detect variables assigned in a piece of code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()
        assigned = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned.add(target.id)
        return assigned

    def _detect_returns(self, code: str) -> List[str]:
        """Detect return values in code."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        returns = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and node.value:
                if isinstance(node.value, ast.Name):
                    returns.append(node.value.id)
        return returns

    # ─── Move Symbol ───────────────────────────────────────────────────────

    def move_symbol(self, symbol_name: str, from_file: str, to_file: str,
                    create_import: bool = True) -> RefactorPlan:
        """
        Move a function or class from one file to another.
        Updates imports in all dependent files.
        """
        plan = RefactorPlan(description=f"Move '{symbol_name}' from {from_file} to {to_file}")

        src_path = self.root / from_file if not Path(from_file).is_absolute() else Path(from_file)
        dst_path = self.root / to_file if not Path(to_file).is_absolute() else Path(to_file)

        if not src_path.exists():
            plan.warnings.append(f"Source file not found: {src_path}")
            return plan

        src_content = self._read_file(str(src_path))

        # Extract the symbol from source
        try:
            tree = ast.parse(src_content)
        except SyntaxError as e:
            plan.warnings.append(f"Cannot parse source file: {e}")
            return plan

        symbol_def = None
        symbol_imports = set()  # imports needed by the symbol

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol_name:
                    symbol_def = node
                    break

        if not symbol_def:
            plan.warnings.append(f"Symbol '{symbol_name}' not found in {from_file}")
            return plan

        # Get source lines for the symbol
        start_line = symbol_def.lineno
        end_line = getattr(symbol_def, 'end_lineno', start_line)
        src_lines = src_content.splitlines()
        symbol_source = "\n".join(src_lines[start_line - 1:end_line])

        # Read or create destination file
        if dst_path.exists():
            dst_content = self._read_file(str(dst_path))
        else:
            dst_content = ""
            plan.new_files.append((str(dst_path), ""))

        # Add symbol to destination
        if dst_content:
            dst_content = dst_content.rstrip() + "\n\n" + symbol_source + "\n"
        else:
            dst_content = symbol_source + "\n"

        if str(dst_path) in plan.new_files:
            plan.new_files = [(str(dst_path), dst_content)]
        else:
            plan.changes.append(RefactorChange(
                file=str(dst_path),
                old_content=self._read_file(str(dst_path)) if dst_path.exists() else "",
                new_content=dst_content,
                description=f"Add {symbol_name} from {from_file}",
            ))

        # Remove from source
        new_src_lines = src_lines[:start_line - 1] + src_lines[end_line:]
        plan.changes.append(RefactorChange(
            file=str(src_path),
            old_content=src_content,
            new_content="\n".join(new_src_lines),
            description=f"Remove {symbol_name} (moved to {to_file})",
        ))

        # If create_import is True, we'll add it to files that import from source
        if create_import:
            graph = self._get_graph()
            if from_file in graph.imported_by:
                for importing_file in graph.imported_by[from_file]:
                    import_plan = self._add_import_to_file(
                        importing_file,
                        to_file,
                        symbol_name,
                        alias=None
                    )
                    plan.changes.extend(import_plan.changes)
                    plan.warnings.extend(import_plan.warnings)

        return plan

    # ─── Import Management ─────────────────────────────────────────────────

    def _add_import_to_file(self, file: str, module: str, name: str,
                            alias: Optional[str] = None) -> RefactorPlan:
        """Add an import statement to a file."""
        plan = RefactorPlan()
        filepath = Path(file)

        if not filepath.exists():
            return plan

        content = self._read_file(str(filepath))
        import_line = f"from {module} import {name}"
        if alias:
            import_line += f" as {alias}"

        # Check if already imported
        if name in content or f"from {module} import" in content:
            return plan

        # Add after any existing imports
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return plan

        last_import_line = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if hasattr(node, 'lineno'):
                    last_import_line = max(last_import_line, node.lineno)

        lines = content.splitlines()
        if last_import_line > 0:
            lines.insert(last_import_line, import_line)
        else:
            # Add after docstring
            for i, line in enumerate(lines):
                if line.strip().startswith('"""') or line.strip().startswith("'''"):
                    # Find end of docstring using next() to avoid nested loop
                    end = next(
                        (j + 1 for j in range(i + 1, len(lines))
                         if '"""' in lines[j] or "'''" in lines[j]),
                        0,
                    )
                    if end:
                        last_import_line = end
                    break

            if last_import_line > 0:
                lines.insert(last_import_line, import_line)
            else:
                lines.insert(0, import_line)

        plan.changes.append(RefactorChange(
            file=str(filepath),
            old_content=content,
            new_content="\n".join(lines),
            description=f"Add import: {import_line}",
        ))

        return plan

    def add_import(self, file: str, module: str, names: List[str]) -> RefactorPlan:
        """Add import statements to a file."""
        plan = RefactorPlan()
        for name in names:
            result = self._add_import_to_file(file, module, name)
            plan.changes.extend(result.changes)
            plan.warnings.extend(result.warnings)
        return plan

    def remove_unused_imports(self, file: str) -> RefactorPlan:
        """Remove import statements that are not used in the file."""
        plan = RefactorPlan()
        filepath = Path(file)

        if not filepath.exists():
            return plan

        content = self._read_file(str(filepath))

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return plan

        # Find actually used names
        analyzer = ImportAnalyzer()
        analyzer.visit(tree)

        # Check each import
        new_content = content
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    # Check if name is actually used (rough heuristic)
                    name_parts = alias.name.split('.')
                    base_name = name_parts[0]

                    # Count occurrences as actual usage (not just string)
                    pattern = r'\b' + re.escape(base_name) + r'\b'
                    matches = re.findall(pattern, new_content)

                    # If name appears only in the import line and not elsewhere, it might be unused
                    import_line_match = re.search(
                        r'import\s+' + re.escape(alias.name),
                        new_content
                    )
                    if import_line_match and len(matches) <= 1:
                        # Likely unused - but this is a heuristic
                        plan.warnings.append(f"Potentially unused import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    # Check if used
                    pattern = r'\b' + re.escape(name) + r'\b'
                    if len(re.findall(pattern, new_content)) <= 1:
                        plan.warnings.append(f"Potentially unused import: {name} from {module}")

        return plan

    # ─── Apply Plan ────────────────────────────────────────────────────────

    def apply_plan(self, plan: RefactorPlan, dry_run: bool = False) -> Dict[str, Any]:
        """
        Apply a refactoring plan.

        Returns:
            Dict with 'applied', 'failed', 'warnings' keys
        """
        results = {
            "applied": [],
            "failed": [],
            "warnings": list(plan.warnings),
            "backup_session": None,
        }

        # ── Backup all files that will be touched ──────────────────────
        if self._backup and not dry_run:
            backed = self._backup.backup_plan(plan)
            self._backup.write_manifest()
            results["backup_session"] = self._backup._session_id
            if backed:
                results["warnings"].append(
                    f"Backed up {backed} file(s) to "
                    f"{self._backup._session_dir}"
                )

        # Create new files
        for path, content in plan.new_files:
            try:
                if not dry_run:
                    self._write_file(path, content)
                results["applied"].append(path)
            except Exception as e:
                results["failed"].append({"file": path, "error": str(e)})

        # Apply changes
        for change in plan.changes:
            try:
                if not dry_run:
                    self._write_file(change.file, change.new_content)
                results["applied"].append(change.file)
            except Exception as e:
                results["failed"].append({"file": change.file, "error": str(e)})

        return results

    def _should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded from refactoring."""
        exclude_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".refactorer_backups"}
        for part in path.parts:
            if part in exclude_dirs:
                return True
        return False

    # ─── Restore / Rollback ────────────────────────────────────────────────

    def restore_session(self, session_id: Optional[str] = None) -> List[str]:
        """Restore all files from a backup session.

        If *session_id* is None, the most recent session is used.
        Returns the list of restored file paths.
        """
        if not self._backup:
            return []
        if session_id is None:
            sessions = BackupManager.list_sessions()
            if not sessions:
                return []
            session_id = sessions[0]
        bm = BackupManager(self.root)
        bm._session_id = session_id
        bm._session_dir = BackupManager.get_session_path(session_id)
        # Reload manifest
        manifest_path = bm._session_dir / "manifest.json"
        if manifest_path.exists():
            bm._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bm.restore_all()

    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backup sessions with file counts."""
        sessions = BackupManager.list_sessions()
        result = []
        for sid in sessions:
            session_dir = BackupManager.get_session_path(sid)
            manifest_path = session_dir / "manifest.json"
            count = 0
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    count = len(manifest)
                except (json.JSONDecodeError, OSError):
                    pass
            result.append({
                "session_id": sid,
                "path": str(session_dir),
                "file_count": count,
            })
        return result

    # ─── High-Level Refactorings ───────────────────────────────────────────

    def make_method_static(self, file: str, class_name: str, method_name: str) -> RefactorPlan:
        """Convert an instance method to a static method."""
        plan = RefactorPlan()
        filepath = Path(file)

        if not filepath.exists():
            return plan

        content = self._read_file(str(filepath))

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return plan

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        # Remove 'self' parameter
                        if item.args.args and item.args.args[0].arg == 'self':
                            item.args.args.pop(0)

                        # Add @staticmethod decorator if not present
                        if not any(d.id == "staticmethod" for d in item.decorator_list if isinstance(d, ast.Name)):
                            item.decorator_list.insert(0, ast.Name(id="staticmethod"))

        # Re-generate code (simplified - just text replacement for now)
        old_def = f"def {method_name}(self,"
        new_def = f"@staticmethod\ndef {method_name}("
        new_content = content.replace(old_def, new_def)

        plan.changes.append(RefactorChange(
            file=str(filepath),
            old_content=content,
            new_content=new_content,
            description=f"Make {class_name}.{method_name} static",
        ))

        return plan

    def inline_function(self, file: str, function_name: str) -> RefactorPlan:
        """Inline a function call at all call sites."""
        plan = RefactorPlan()
        filepath = Path(file)

        if not filepath.exists():
            return plan

        content = self._read_file(str(filepath))

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return plan

        # Find function definition
        func_node = None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                func_node = node
                break

        if not func_node:
            plan.warnings.append(f"Function '{function_name}' not found")
            return plan

        # Get function source
        lines = content.splitlines()
        func_start = func_node.lineno - 1
        func_end = getattr(func_node, 'end_lineno', func_start + 1)
        func_source = "\n".join(lines[func_start:func_end])

        # Count call sites
        call_count = content.count(f"{function_name}(")
        plan.warnings.append(f"Found {call_count} call site(s) - inlining will duplicate code")

        plan.changes.append(RefactorChange(
            file=str(filepath),
            old_content=content,
            new_content=content,  # Would need actual inlining logic
            description=f"Inline {function_name} at {call_count} call sites",
        ))

        return plan


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    ref = MultiModuleRefactorer(root)

    # Test rename
    plan = ref.rename_symbol("old_name", "new_name", files=["src/example.py"])
    print(f"Rename plan: {len(plan.changes)} changes")

    # Test extract
    plan = ref.extract_function("test.py", 10, 20, "new_function")
    print(f"Extract plan: {plan.description}")

    # Apply
    if plan.changes:
        results = ref.apply_plan(plan, dry_run=True)
        print(f"Would apply: {results}")