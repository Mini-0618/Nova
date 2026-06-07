"""
Code Analyzer - Call graph builder and impact analysis using AST.
Builds cross-file function call graphs for Python projects.
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


class CallGraphBuilder:
    """
    Build function call graphs from Python source files using ast module.

    Usage:
        builder = CallGraphBuilder()
        graph = builder.build_graph("my_project/")
        callers = builder.find_callers("my_func", graph)
        callees = builder.find_callees("my_func", graph)
        impacted = builder.impact_analysis(["my_project/core.py"], graph)
    """

    def __init__(self):
        # {qualified_name: [called_qualified_names]}
        self._graph: Dict[str, List[str]] = {}
        # {qualified_name: file_path}
        self._func_to_file: Dict[str, str] = {}
        # {file_path: {imported_name: source_module}}
        self._file_imports: Dict[str, Dict[str, str]] = {}
        # {module_name: file_path}
        self._module_map: Dict[str, str] = {}

    def build_graph(self, project_dir: str) -> Dict[str, List[str]]:
        """
        Build a call graph for all Python files in a project directory.

        Returns dict: {function_qualified_name: [called_function_names]}
        """
        project_dir = os.path.abspath(project_dir)
        self._graph = {}
        self._func_to_file = {}
        self._file_imports = {}
        self._module_map = {}
        self._project_dir = project_dir

        py_files = self._collect_py_files(project_dir)
        if not py_files:
            return {}

        # Phase 1: Parse all files
        parsed = {}
        for fpath in py_files:
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    source = f.read()
                tree = ast.parse(source, filename=fpath)
                parsed[fpath] = tree
            except (SyntaxError, UnicodeDecodeError):
                continue

        # Build module map
        for fpath in parsed:
            module = self._file_to_module(fpath, project_dir)
            self._module_map[module] = fpath

        # Phase 2: Extract imports and function defs
        file_info = {}
        for fpath, tree in parsed.items():
            imports = self._extract_imports(tree, fpath, project_dir)
            funcs = self._extract_functions(tree)
            self._file_imports[fpath] = imports
            file_info[fpath] = funcs

        # Phase 3: Build the call graph
        for fpath, tree in parsed.items():
            self._process_file(fpath, tree, file_info)

        return dict(self._graph)

    def find_callers(self, func_name: str, graph: Optional[Dict[str, List[str]]] = None) -> List[str]:
        """
        Find all functions that call the given function.
        Searches by exact name or suffix match (module.func).
        """
        g = graph if graph is not None else self._graph
        callers = []
        for func, callees in g.items():
            for callee in callees:
                if callee == func_name or callee.endswith(f".{func_name}"):
                    callers.append(func)
                    break
        return sorted(callers)

    def find_callees(self, func_name: str, graph: Optional[Dict[str, List[str]]] = None) -> List[str]:
        """
        Find all functions called by the given function.
        Searches by exact name or suffix match.
        """
        g = graph if graph is not None else self._graph
        for func, callees in g.items():
            if func == func_name or func.endswith(f".{func_name}"):
                return sorted(callees)
        return []

    def impact_analysis(self, changed_files: List[str], graph: Optional[Dict[str, List[str]]] = None) -> List[str]:
        """
        Given a list of changed file paths, find all other files that may be impacted.
        Impact = files containing functions that call functions defined in changed files.
        """
        g = graph if graph is not None else self._graph
        changed_files = [os.path.abspath(f) for f in changed_files]

        # Collect all functions defined in changed files
        affected_funcs: Set[str] = set()
        for func, fpath in self._func_to_file.items():
            if os.path.abspath(fpath) in changed_files:
                affected_funcs.add(func)

        # Find callers of those functions
        impacted_files: Set[str] = set()
        for caller_func, callees in g.items():
            for callee in callees:
                if callee in affected_funcs:
                    caller_file = self._func_to_file.get(caller_func)
                    if caller_file and os.path.abspath(caller_file) not in changed_files:
                        impacted_files.add(caller_file)

        return sorted(impacted_files)

    # ─── Internals ───────────────────────────────────────────────────────

    def _collect_py_files(self, project_dir: str) -> List[str]:
        """Collect all .py files, skipping hidden dirs and __pycache__."""
        py_files = []
        for root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for fname in files:
                if fname.endswith(".py"):
                    py_files.append(os.path.join(root, fname))
        return sorted(py_files)

    def _file_to_module(self, fpath: str, project_dir: str) -> str:
        """Convert a file path to a module path (e.g., runtime/agent.py -> runtime.agent)."""
        rel = os.path.relpath(fpath, project_dir)
        rel = rel.replace(os.sep, "/")
        if rel.endswith(".py"):
            rel = rel[:-3]
        if rel.endswith("/__init__"):
            rel = rel[:-9]
        return rel.replace("/", ".")

    def _extract_imports(self, tree: ast.AST, fpath: str, project_dir: str) -> Dict[str, str]:
        """
        Extract import mappings: {imported_name: module_name}.

        Resolves relative imports using the file's position in the project.
        """
        imports = {}
        current_dir = os.path.dirname(os.path.abspath(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = getattr(node, "level", 0)

                if level > 0:
                    # Relative import: walk up `level` directories from current file
                    base_dir = current_dir
                    for _ in range(level):
                        base_dir = os.path.dirname(base_dir)

                    for alias in node.names:
                        name = alias.asname or alias.name
                        if module:
                            # from .module import name -> resolve module path
                            target_parts = module.split(".")
                            target_dir = os.path.join(base_dir, *target_parts)
                            imports[name] = self._dir_to_module(target_dir, project_dir)
                        else:
                            # from . import utils -> utils is a sub-module
                            target_dir = os.path.join(base_dir, name)
                            imports[name] = self._dir_to_module(target_dir, project_dir)
                else:
                    for alias in node.names:
                        name = alias.asname or alias.name
                        imports[name] = module

        return imports

    def _dir_to_module(self, dir_path: str, project_dir: str) -> str:
        """Convert a directory path to a module name relative to project_dir."""
        dir_path = os.path.normpath(dir_path)
        project_dir = os.path.normpath(project_dir)
        if dir_path.startswith(project_dir):
            rel = os.path.relpath(dir_path, project_dir)
            return rel.replace(os.sep, ".")
        return os.path.basename(dir_path)

    def _extract_functions(self, tree: ast.AST) -> List[ast.FunctionDef]:
        """Extract top-level and class method function definitions."""
        funcs = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                funcs.append(node)
            elif isinstance(node, ast.ClassDef):
                for item in ast.iter_child_nodes(node):
                    if isinstance(item, ast.FunctionDef):
                        funcs.append(item)
        return funcs

    def _get_class_name(self, tree: ast.AST, func_node: ast.FunctionDef) -> Optional[str]:
        """Get the class name if func_node is a method."""
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                for item in ast.iter_child_nodes(node):
                    if item is func_node:
                        return node.name
        return None

    def _resolve_call_name(self, call_node: ast.Call, imports: Dict[str, str]) -> Optional[str]:
        """Resolve a Call node to a qualified function name."""
        func = call_node.func

        if isinstance(func, ast.Name):
            # Direct call: func_name(...)
            name = func.id
            if name in imports:
                return f"{imports[name]}.{name}"
            return name

        elif isinstance(func, ast.Attribute):
            # Attribute call: obj.method(...)
            if isinstance(func.value, ast.Name):
                obj_name = func.value.id
                method_name = func.attr
                if obj_name in imports:
                    return f"{imports[obj_name]}.{method_name}"
                return f"{obj_name}.{method_name}"

        return None

    def _process_file(self, fpath: str, tree: ast.AST, file_info: Dict):
        """Process a single file: register functions and their calls."""
        module = self._file_to_module(fpath, self._project_dir)
        imports = self._file_imports.get(fpath, {})
        funcs = file_info.get(fpath, [])

        for func_def in funcs:
            class_name = self._get_class_name(tree, func_def)
            if class_name:
                qualified = f"{module}.{class_name}.{func_def.name}"
            else:
                qualified = f"{module}.{func_def.name}"

            self._func_to_file[qualified] = fpath

            # Collect calls inside this function
            callees = set()
            for node in ast.walk(func_def):
                if isinstance(node, ast.Call):
                    resolved = self._resolve_call_name(node, imports)
                    if resolved:
                        callees.add(resolved)

            self._graph[qualified] = sorted(callees)


# ─── CLI Entry Point ─────────────────────────────────────────────────────

def main():
    """CLI: python -m runtime.code_analyzer <project_dir>"""
    if len(sys.argv) < 2:
        print("Usage: python -m runtime.code_analyzer <project_dir>")
        sys.exit(1)

    project_dir = sys.argv[1]
    if not os.path.isdir(project_dir):
        print(f"Error: '{project_dir}' is not a directory")
        sys.exit(1)

    builder = CallGraphBuilder()
    graph = builder.build_graph(project_dir)

    if not graph:
        print("No functions found.")
        sys.exit(0)

    print(f"=== Call Graph: {len(graph)} functions ===\n")

    for func, callees in sorted(graph.items()):
        if callees:
            print(f"{func}")
            for c in callees:
                print(f"  -> {c}")
        else:
            print(f"{func} (leaf)")

    print(f"\n=== Summary ===")
    print(f"Total functions: {len(graph)}")
    total_calls = sum(len(v) for v in graph.values())
    print(f"Total calls: {total_calls}")

    # Show most-called functions
    call_counts: Dict[str, int] = defaultdict(int)
    for callees in graph.values():
        for c in callees:
            call_counts[c] += 1
    if call_counts:
        print(f"\n=== Most Called ===")
        for func, count in sorted(call_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  {count}x {func}")


if __name__ == "__main__":
    main()
