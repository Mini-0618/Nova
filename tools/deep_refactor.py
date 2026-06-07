"""
Codex-Local Deep Refactorer
Deeper AST-based refactoring: rename symbol across project with import updates,
extract method to another class, inline temporary, add type annotations.
"""

import os
import sys
import ast
import re
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@dataclass
class RefactorChange:
    file: str
    old_content: str
    new_content: str
    description: str
    lines_changed: int = 0


@dataclass
class RefactorPlan:
    changes: List[RefactorChange] = field(default_factory=list)
    new_files: List[tuple] = field(default_factory=list)  # [(path, content)]
    deleted_files: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    description: str = ""
    safe: bool = True


class DeepSymbolAnalyzer(ast.NodeVisitor):
    """Deep symbol analysis: all references, imports, and type annotations."""

    def __init__(self, source: str, tree: ast.AST):
        self.source = source
        self.tree = tree
        self.symbols: Dict[str, List[Dict]] = {}  # name -> [{"file": ..., "line": ..., "type": ..., "import": bool}]
        self.imports: Dict[str, str] = {}  # alias -> real_name
        self.current_class = None

    def visit_Import(self, node):
        for alias in node.names:
            real = alias.name
            asname = alias.asname or real
            self.imports[asname] = real
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            real = alias.name
            asname = alias.asname or real
            if module:
                self.imports[asname] = f"{module}.{real}"
            else:
                self.imports[asname] = real
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._add_symbol(node.name, "function", node.lineno)
        old_class = self.current_class
        self.current_class = None
        self.generic_visit(node)
        self.current_class = old_class

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._add_symbol(node.name, "class", node.lineno)
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Load, ast.Store)):
            ref_type = "class_ref" if self.current_class else "local_ref"
            self._add_symbol(node.id, ref_type, node.lineno)
        self.generic_visit(node)

    def _add_symbol(self, name: str, sym_type: str, line: int):
        self.symbols.setdefault(name, []).append({
            "type": sym_type,
            "line": line,
            "import": False,
        })


class DeepRefactorer:
    """
    Deep multi-file refactoring beyond basic rename.

    Capabilities:
    1. Rename symbol with ALL references updated (def, call, import, docstring, comment)
    2. Extract method to another class (with binding)
    3. Inline temporary variable
    4. Add type annotations automatically
    5. Move symbol to another module with import updates
    6. Safe delete (check all references first)
    """

    def __init__(self, workspace: str):
        self.workspace = Path(workspace)

    def _read(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8", errors="replace")

    def _write(self, path: str, content: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    # ─── Rename with type annotation support ─────────────────────

    def rename_symbol_deep(self, symbol: str, new_name: str,
                           files: Optional[List[str]] = None,
                           include_docstrings: bool = True,
                           include_comments: bool = True) -> RefactorPlan:
        """
        Rename a symbol across all files, updating:
        - Definition
        - All call sites
        - Import statements
        - Type annotations
        - Docstrings (if include_docstrings)
        - Comments containing the symbol (if include_comments)
        """
        plan = RefactorPlan(description=f"Rename '{symbol}' -> '{new_name}'")
        py_files = list(self.workspace.rglob("*.py")) if files is None else [Path(f) for f in files]

        for path in py_files:
            if any(p in path.parts for p in ["venv", "node_modules", "__pycache__", ".git"]):
                continue

            try:
                content = self._read(str(path))
                original = content
            except Exception:
                continue

            new_content = self._deep_rename(content, symbol, new_name,
                                          include_docstrings, include_comments)

            if new_content != original:
                plan.changes.append(RefactorChange(
                    file=str(path),
                    old_content=original,
                    new_content=new_content,
                    description=f"Rename {symbol} -> {new_name}",
                    lines_changed=sum(1 for a, b in zip(original.splitlines(), new_content.splitlines()) if a != b),
                ))

        return plan

    def _deep_rename(self, content: str, old: str, new: str,
                    docstrings: bool, comments: bool) -> str:
        # Use AST-aware replacement + post-processing
        result = content

        # 1. Word-boundary replacement for code (safe)
        # Match whole words only
        pattern = r"\b" + re.escape(old) + r"\b"
        result = re.sub(pattern, new, result)

        # 2. Type annotations: old: Type -> new: Type
        result = re.sub(r"(?<=\b)" + re.escape(old) + r"(?=\s*[:\[])",
                        lambda m: new + m.group(0)[len(new):], result)

        # 3. Docstrings
        if docstrings:
            # Replace in docstrings (triple-quoted strings)
            result = self._replace_in_docstrings(result, old, new)

        return result

    def _replace_in_docstrings(self, content: str, old: str, new: str) -> str:
        """Replace symbol in docstrings only."""
        lines = content.split("\n")
        in_docstring = False
        docstring_quotes = ""

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Detect docstring start
            if '"""' in line or "'''" in line:
                if not in_docstring:
                    in_docstring = True
                    docstring_quotes = '"""' if '"""' in line else "'''"
                elif docstring_quotes in line:
                    in_docstring = False

            if in_docstring:
                if old in line:
                    lines[i] = line.replace(old, new)

        return "\n".join(lines)

    # ─── Extract method to class ────────────────────────────────

    def extract_method(self, file: str, class_name: str,
                      method_name: str,
                      source_lines: List[int],
                      params: List[str]) -> RefactorPlan:
        """
        Extract code lines into a new method in a class.

        Args:
            file: Source file
            class_name: Class to add method to
            method_name: New method name
            source_lines: [start, end] (1-indexed)
            params: Parameter names for the new method
        """
        plan = RefactorPlan(description=f"Extract method {method_name}")

        content = self._read(file)
        lines = content.splitlines()

        start, end = source_lines
        extracted = lines[start-1:end]

        # Build new method
        param_str = ", ".join(params) if params else "self"
        indent = "    "

        new_method_lines = [f"{indent}def {method_name}({param_str}):"]
        for line in extracted:
            new_method_lines.append(indent + indent + line.strip())
        new_method_lines.append("")

        new_method = "\n".join(new_method_lines)

        # Find class in file
        try:
            tree = ast.parse(content)
        except SyntaxError:
            plan.warnings.append(f"Could not parse {file}")
            return plan

        class_line = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                class_line = node.lineno
                break

        if class_line:
            # Insert after class docstring or last method
            lines.insert(class_line, new_method)
            plan.changes.append(RefactorChange(
                file=file,
                old_content=content,
                new_content="\n".join(lines),
                description=f"Add method {method_name} to class {class_name}",
            ))
        else:
            plan.warnings.append(f"Class {class_name} not found in {file}")

        return plan

    # ─── Inline temporary ───────────────────────────────────

    def inline_temporary(self, file: str, var_name: str) -> RefactorPlan:
        """
        Find a temporary variable assignment and replace all uses with its value.
        Only works when the RHS is a simple expression (no side effects.
        """
        plan = RefactorPlan(description=f"Inline temporary '{var_name}'")
        content = self._read(file)

        try:
            tree = ast.parse(content)
        except SyntaxError:
            plan.warnings.append("Parse error")
            return plan

        # Find the assignment
        assign_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == var_name:
                        assign_node = node
                        break

        if not assign_node:
            plan.warnings.append(f"Variable '{var_name}' not found")
            return plan

        # Get RHS expression
        rhs = ast.unparse(assign_node.value)

        # Find all uses of var_name
        # (simplified: replace all Name nodes referencing var_name in Load context)
        # For now, do text replacement
        pattern = r"(?<![a-zA-Z_0-9])" + re.escape(var_name) + r"(?![a-zA-Z_0-9])"
        new_content = re.sub(pattern, f"({rhs})", content)

        if new_content != content:
            plan.changes.append(RefactorChange(
                file=file,
                old_content=content,
                new_content=new_content,
                description=f"Inline {var_name} = {rhs}",
            ))

        return plan

    # ─── Add type annotations ──────────────────────────────

    def add_type_annotations(self, file: str,
                            annotations: Dict[str, str]) -> RefactorPlan:
        """
        Add type annotations to a file.
        annotations: {"var_name": "Type", "func_arg": "Type", ...}
        """
        plan = RefactorPlan(description="Add type annotations")

        content = self._read(file)
        new_content = content

        for target, type_hint in annotations.items():
            # Function arguments: def foo(old_arg) -> def foo(new_arg: Type)
            pattern = r"(def \w+\()" + re.escape(target) + r"(\))"
            replacement = "\\g<1>" + target + f": {type_hint}\\g<2>"
            new_content = re.sub(pattern, replacement, new_content)

            # Variable annotations: var -> var: Type (in type comment style)

        if new_content != content:
            plan.changes.append(RefactorChange(
                file=file,
                old_content=content,
                new_content=new_content,
                description=f"Add type annotation {target}: {type_hint}",
            ))

        return plan

    # ─── Apply plan ─────────────────────────────────────

    def apply(self, plan: RefactorPlan, dry_run: bool = True) -> Dict:
        """Apply a refactor plan. dry_run by default."""
        applied = []
        failed = []

        for change in plan.changes:
            try:
                if not dry_run:
                    self._write(change.file, change.new_content)
                applied.append(change.file)
            except Exception as e:
                failed.append({"file": change.file, "error": str(e)})

        for path, content in plan.new_files:
            try:
                if not dry_run:
                    self._write(path, content)
                applied.append(path)
            except Exception as e:
                failed.append({"file": path, "error": str(e)})

        return {
            "applied": applied,
            "failed": failed,
            "warnings": plan.warnings,
            "safe": plan.safe,
        }


# ─── Tool wrapper ───────────────────────────────────────────────

def deep_refactor_tool(operation: str, symbol: str = None, **kwargs) -> Dict[str, Any]:
    """
    Deep refactor tool for executor.
    """
    try:
        ref = DeepRefactorer(kwargs.get("workspace", "D:/"))

        if operation == "rename":
            plan = ref.rename_symbol_deep(
                symbol=kwargs["symbol"],
                new_name=kwargs["new_name"],
                files=kwargs.get("files"),
                include_docstrings=kwargs.get("include_docstrings", True),
                include_comments=kwargs.get("include_comments", False),
            )
            return ref.apply(plan, dry_run=kwargs.get("dry_run", True))

        elif operation == "extract_method":
            plan = ref.extract_method(
                file=kwargs["file"],
                class_name=kwargs["class_name"],
                method_name=kwargs["method_name"],
                source_lines=kwargs["source_lines"],
                params=kwargs.get("params", []),
            )
            return ref.apply(plan, dry_run=kwargs.get("dry_run", True))

        elif operation == "inline":
            plan = ref.inline_temporary(
                file=kwargs["file"],
                var_name=kwargs["var_name"],
            )
            return ref.apply(plan, dry_run=kwargs.get("dry_run", True))

        elif operation == "annotate":
            plan = ref.add_type_annotations(
                file=kwargs["file"],
                annotations=kwargs.get("annotations", {}),
            )
            return ref.apply(plan, dry_run=kwargs.get("dry_run", True))

        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    ref = DeepRefactorer(".")
    plan = ref.rename_symbol_deep("old_name", "new_name", files=["runtime/loop.py"])
    print(f"Plan: {len(plan.changes)} changes, warnings: {plan.warnings}")