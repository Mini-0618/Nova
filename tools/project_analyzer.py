"""
Codex-Local Project Structure Analyzer
Uses AST parsing to understand project structure, module dependencies,
class/function hierarchies, and import graphs across large codebases.
"""

import os
import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict


@dataclass
class Symbol:
    """A function, class, or variable at a location."""
    name: str
    type: str  # 'function' | 'class' | 'method' | 'module_var'
    file: str
    line: int
    end_line: Optional[int] = None
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    signature: Optional[str] = None  # human-readable signature
    is_async: bool = False
    is_property: bool = False


@dataclass
class Import:
    """An import statement."""
    file: str
    module: str
    names: List[str]  # ['os', 'Path'] or ['*']
    line: int
    level: int = 0  # relative import depth


@dataclass
class Module:
    """A module (file) in the project."""
    path: str
    relative_path: str
    size_lines: int
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[Import] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ProjectGraph:
    """Complete project structure."""
    root: str
    modules: Dict[str, Module] = field(default_factory=dict)
    imports: Dict[str, List[str]] = field(default_factory=dict)  # file -> [files it imports]
    imported_by: Dict[str, List[str]] = field(default_factory=dict)  # file -> [files that import it]
    all_symbols: Dict[str, List[Symbol]] = field(default_factory=dict)  # name -> [symbols with that name]
    classes: Dict[str, List[Symbol]] = field(default_factory=dict)  # class name -> symbols
    functions: Dict[str, List[Symbol]] = field(default_factory=dict)  # func name -> symbols


class ProjectAnalyzer:
    """
    Analyzes a project directory and builds a complete structure graph.

    Usage:
        analyzer = ProjectAnalyzer("D:/myproject")
        graph = analyzer.analyze()
        print(graph.classes["MyClass"])  # All definitions of MyClass
        print(graph.imports["src/utils.py"])  # What utils.py imports
    """

    LANGUAGE_PATTERNS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
    }

    def __init__(self, root: str, exclude_patterns: Optional[List[str]] = None):
        self.root = Path(root).resolve()
        self.exclude_patterns = exclude_patterns or [
            "node_modules", ".git", "__pycache__", ".pytest_cache",
            "venv", ".venv", "env", ".env", "dist", "build",
            "*.pyc", "*.pyo", "*.so", "*.dll", "*.exe",
            ".DS_Store", "Thumbs.db",
        ]

    def should_exclude(self, path: Path) -> bool:
        name = path.name
        for pattern in self.exclude_patterns:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif name == pattern:
                return True
            elif pattern in str(path):
                return True
        return False

    def find_files(self, root: Path) -> List[Path]:
        """Find all source files in the project."""
        files = []
        for item in root.rglob("*"):
            if item.is_file() and not self.should_exclude(item):
                ext = item.suffix.lower()
                if ext in self.LANGUAGE_PATTERNS:
                    files.append(item)
        return files

    # ─── Python AST Parser ────────────────────────────────────────────────

    def parse_python_file(self, path: Path) -> Module:
        """Parse a Python file into a Module."""
        rel_path = str(path.relative_to(self.root))
        module = Module(
            path=str(path),
            relative_path=rel_path,
            size_lines=0,
        )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            module.size_lines = len(content.splitlines())
            tree = ast.parse(content, filename=str(path))
        except SyntaxError as e:
            module.errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
            return module
        except Exception as e:
            module.errors.append(f"Parse error: {e}")
            return module

        # Extract imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imp = Import(
                    file=str(path),
                    module="",
                    names=[alias.name for alias in node.names],
                    line=node.lineno or 0,
                )
                module.imports.append(imp)
            elif isinstance(node, ast.ImportFrom):
                imp = Import(
                    file=str(path),
                    module=node.module or "",
                    names=[alias.name for alias in node.names],
                    line=node.lineno or 0,
                    level=node.level,
                )
                module.imports.append(imp)

        # Extract top-level definitions
        for node in tree.body:
            sym = self._extract_python_symbol(node, str(path))
            if sym:
                module.symbols.append(sym)

        return module

    def _extract_python_symbol(self, node, filepath: str) -> Optional[Symbol]:
        """Extract a symbol from a Python AST node."""
        try:
            docstring = ast.get_docstring(node)
        except TypeError:
            docstring = None

        if isinstance(node, ast.ClassDef):
            bases = [b.attr if isinstance(b, ast.Attribute) else (b.id if isinstance(b, ast.Name) else str(b))
                     for b in getattr(node, 'bases', [])]
            sym = Symbol(
                name=node.name,
                type="class",
                file=filepath,
                line=node.lineno,
                end_line=node.end_lineno,
                docstring=docstring,
                decorators=[self._get_decorator_name(d) for d in getattr(node, 'decorator_list', [])],
            )
            # Extract methods
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_sym = self._extract_python_symbol(item, filepath)
                    if method_sym:
                        method_sym.type = "method"
                        method_sym.name = f"{node.name}.{method_sym.name}"
                        module.symbols.append(method_sym) if 'module.symbols' in dir() else None
                        sym.name += f" (method: {item.name})"  # annotate

            return sym

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_property = any(
                self._get_decorator_name(d) in ("property", "cached_property")
                for d in getattr(node, 'decorator_list', [])
            )
            args = self._format_args(node.args)
            return Symbol(
                name=node.name,
                type="async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                file=filepath,
                line=node.lineno,
                end_line=node.end_lineno,
                docstring=docstring,
                decorators=[self._get_decorator_name(d) for d in getattr(node, 'decorator_list', [])],
                signature=f"{node.name}({args})",
                is_async=isinstance(node, ast.AsyncFunctionDef),
                is_property=is_property,
            )

        return None

    def _get_decorator_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "unknown"

    def _format_args(self, args) -> str:
        parts = []
        defaults = list(args.defaults)
        num_defaults = len(defaults)
        num_args = len(args.args)

        for i, arg in enumerate(args.args):
            default_idx = i - num_args + num_defaults
            if default_idx >= 0:
                default = defaults[default_idx]
                parts.append(f"{arg.arg}=<default>")
            else:
                parts.append(arg.arg)

        if args.vararg:
            parts.append(f"*{args.vararg.arg}")
        if args.kwarg:
            parts.append(f"**{args.kwarg.arg}")
        return ", ".join(parts)

    # ─── JavaScript Parser (simplified) ───────────────────────────────────

    def parse_javascript_file(self, path: Path) -> Module:
        """Parse a JavaScript/TypeScript file (simplified regex-based)."""
        rel_path = str(path.relative_to(self.root))
        module = Module(
            path=str(path),
            relative_path=rel_path,
            size_lines=0,
        )

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            module.size_lines = len(content.splitlines())
        except Exception as e:
            module.errors.append(f"Read error: {e}")
            return module

        # Extract imports: import X from 'Y', require('Y')
        import_patterns = [
            r"import\s+(?:{[^}]+}|[\w*]+)\s+from\s+['\"]([^'\"]+)['\"]",
            r"import\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        ]
        for pattern in import_patterns:
            for m in re.finditer(pattern, content):
                module.imports.append(Import(
                    file=str(path),
                    module=m.group(1),
                    names=[],
                    line=content[:m.start()].count('\n') + 1,
                ))

        # Extract classes
        class_pattern = r"class\s+(\w+)(?:\s+extends\s+\w+)?\s*{"
        for m in re.finditer(class_pattern, content):
            module.symbols.append(Symbol(
                name=m.group(1),
                type="class",
                file=str(path),
                line=content[:m.start()].count('\n') + 1,
            ))

        # Extract functions: function name( ... ) {  or const name = ( ... ) =>
        func_patterns = [
            r"function\s+(\w+)\s*\(",
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
            r"(?:const|let|var)\s+(\w+)\s*=\s*async\s+function",
        ]
        for pattern in func_patterns:
            for m in re.finditer(pattern, content):
                module.symbols.append(Symbol(
                    name=m.group(1),
                    type="function",
                    file=str(path),
                    line=content[:m.start()].count('\n') + 1,
                ))

        return module

    # ─── Build Project Graph ──────────────────────────────────────────────

    def analyze(self, max_files: int = 1000) -> ProjectGraph:
        """Analyze the project and return a complete graph."""
        files = self.find_files(self.root)[:max_files]
        graph = ProjectGraph(root=str(self.root))

        for path in files:
            ext = path.suffix.lower()
            if ext == ".py":
                module = self.parse_python_file(path)
            elif ext in (".js", ".ts", ".jsx", ".tsx"):
                module = self.parse_javascript_file(path)
            else:
                continue

            graph.modules[module.relative_path] = module

            # Build import graph
            graph.imports[module.relative_path] = []
            for imp in module.imports:
                if imp.module:
                    # Resolve relative imports
                    resolved = self._resolve_import(imp, module.relative_path)
                    if resolved:
                        graph.imports[module.relative_path].append(resolved)
                        graph.imported_by.setdefault(resolved, []).append(module.relative_path)

        # Build symbol index
        for rel_path, module in graph.modules.items():
            for sym in module.symbols:
                if sym.name not in graph.all_symbols:
                    graph.all_symbols[sym.name] = []
                graph.all_symbols[sym.name].append(sym)

                if sym.type in ("class", "method"):
                    if sym.name not in graph.classes:
                        graph.classes[sym.name] = []
                    graph.classes[sym.name].append(sym)

                if sym.type in ("function", "async_function"):
                    if sym.name not in graph.functions:
                        graph.functions[sym.name] = []
                    graph.functions[sym.name].append(sym)

        return graph

    def _resolve_import(self, imp: Import, from_file: str) -> Optional[str]:
        """Resolve a relative import to a module path."""
        module = imp.module
        if not module:
            return None

        # Remove common prefixes
        for prefix in ("src/", "lib/", "app/", "packages/"):
            if module.startswith(prefix):
                return module

        # For relative imports
        if imp.level > 0:
            parts = from_file.split("/")
            for _ in range(imp.level):
                parts.pop()
            if module:
                parts.append(module)
            return "/".join(parts).replace("./", "")

        # Try to find module in project
        for ext in [".py", "/__init__.py", ".js", ".ts"]:
            candidate = f"{module}{ext}"
            if candidate in graph.modules if 'graph' in dir() else False:
                return candidate

        return module

    # ─── High-Level Queries ────────────────────────────────────────────────

    def find_symbol(self, graph: ProjectGraph, name: str) -> List[Symbol]:
        """Find all definitions of a symbol by name."""
        return graph.all_symbols.get(name, [])

    def find_usages(self, graph: ProjectGraph, file_path: str) -> List[str]:
        """Find all files that import or reference a given file."""
        return graph.imported_by.get(file_path, [])

    def find_dependencies(self, graph: ProjectGraph, file_path: str) -> List[str]:
        """Find all files that a given file imports."""
        return graph.imports.get(file_path, [])

    def find_circular_deps(self, graph: ProjectGraph) -> List[List[str]]:
        """Detect circular dependencies in the project."""
        cycles = []
        visited = set()
        path = []

        def dfs(node: str):
            if node in path:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            for dep in graph.imports.get(node, []):
                dfs(dep)
            path.pop()

        for module in graph.modules:
            dfs(module)

        return cycles

    def get_module_hierarchy(self, graph: ProjectGraph) -> Dict[str, List[str]]:
        """Get a directory-tree view of the project."""
        tree = defaultdict(list)
        for rel_path in graph.modules:
            parts = rel_path.split("/")
            if len(parts) > 1:
                tree[parts[0]].append("/".join(parts[1:]))
            else:
                tree["."].append(rel_path)
        return dict(tree)

    def explain_symbol(self, graph: ProjectGraph, name: str) -> str:
        """Give a natural language explanation of a symbol."""
        symbols = graph.all_symbols.get(name, [])
        if not symbols:
            return f"Symbol '{name}' not found in the project."

        lines = [f"## {name}"]
        for sym in symbols:
            lines.append(f"\n### {sym.type} in {sym.file}:{sym.line}")
            if sym.docstring:
                lines.append(f"   {sym.docstring[:100]}")
            if sym.signature:
                lines.append(f"   Signature: `{sym.signature}`")
            if sym.decorators:
                lines.append(f"   Decorators: {', '.join(sym.decorators)}")

        return "\n".join(lines)


# ─── Tool Integration ────────────────────────────────────────────────────────

def analyze_project(root: str, max_files: int = 1000) -> Dict[str, Any]:
    """Analyze a project and return results as a dict."""
    analyzer = ProjectAnalyzer(root)
    graph = analyzer.analyze(max_files)

    return {
        "root": str(analyzer.root),
        "file_count": len(graph.modules),
        "classes": {k: len(v) for k, v in graph.classes.items()},
        "functions": {k: len(v) for k, v in graph.functions.items()},
        "imports": graph.imports,
        "circular_deps": analyzer.find_circular_deps(graph),
        "hierarchy": analyzer.get_module_hierarchy(graph),
    }


# ─── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    analyzer = ProjectAnalyzer(root)
    graph = analyzer.analyze()
    print(f"Analyzed {len(graph.modules)} modules")
    print(f"Classes: {len(graph.classes)}")
    print(f"Functions: {len(graph.functions)}")
    print(f"Circular deps: {analyzer.find_circular_deps(graph)}")