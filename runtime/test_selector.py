"""
Test Selector - Smart test selection based on changed files.

Maps source files to their corresponding test files so that only
relevant tests run when code changes. Reduces CI feedback time.
"""

import os
import sys
import ast
from pathlib import Path
from typing import List, Set, Dict, Optional

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def _find_test_files(test_dir: str = "tests") -> List[Path]:
    """Find all test files in the given directory."""
    test_path = Path(test_dir)
    if not test_path.exists():
        return []
    return sorted(test_path.glob("test_*.py"))


def _parse_imports(filepath: Path) -> Set[str]:
    """Parse a Python file and return the set of imported module names."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except (SyntaxError, OSError):
        return set()

    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def _map_test_to_source(test_file: Path) -> Set[str]:
    """
    Infer which source modules a test file likely tests.
    Strategy: look at imports and the test filename itself.
    """
    source_modules = set()

    # From filename: test_code_analyzer.py -> code_analyzer
    name = test_file.stem  # test_code_analyzer
    if name.startswith("test_"):
        source_modules.add(name[5:])  # code_analyzer

    # From imports in the test file
    imports = _parse_imports(test_file)
    for mod in imports:
        if mod not in ("pytest", "unittest", "os", "sys", "json", "pathlib",
                        "tempfile", "shutil", "time", "datetime", "typing",
                        "collections", "unittest", "asyncio", "io", "re",
                        "subprocess", "threading", "dataclasses", "textwrap"):
            source_modules.add(mod)

    return source_modules


def _changed_to_modules(changed_files: List[str]) -> Set[str]:
    """Convert changed file paths to module names."""
    modules = set()
    for f in changed_files:
        p = Path(f)
        if p.suffix == ".py":
            modules.add(p.stem)
            # Also add parent dir module for packages
            if p.parent.name and p.parent.name != ".":
                modules.add(p.parent.name)
    return modules


def select_tests(
    changed_files: List[str],
    test_dir: str = "tests",
    include_all_on_config_change: bool = True,
) -> List[str]:
    """
    Select test files relevant to the given changed source files.

    Args:
        changed_files: List of changed file paths (relative or absolute).
        test_dir: Directory containing test files.
        include_all_on_config_change: If True, run all tests when config
            files (pytest.ini, setup.py, pyproject.toml, etc.) change.

    Returns:
        List of test file paths to run.
    """
    config_files = {"pytest.ini", "setup.py", "setup.cfg", "pyproject.toml",
                     "tox.ini", "Makefile", "requirements.txt"}

    # Check if any config file changed
    if include_all_on_config_change:
        for f in changed_files:
            if Path(f).name in config_files:
                return [str(t) for t in _find_test_files(test_dir)]

    changed_modules = _changed_to_modules(changed_files)

    test_files = _find_test_files(test_dir)
    selected = []

    for test_file in test_files:
        test_sources = _map_test_to_source(test_file)
        # If any source module this test covers was changed, include it
        if test_sources & changed_modules:
            selected.append(str(test_file))

    # If nothing matched, run all (safe fallback)
    if not selected:
        selected = [str(t) for t in test_files]

    return selected


def select_tests_by_impact(
    changed_files: List[str],
    test_dir: str = "tests",
    source_dir: str = "runtime",
) -> List[str]:
    """
    Enhanced test selection using call-graph impact analysis.
    Falls back to basic select_tests if code_analyzer is unavailable.
    """
    try:
        from runtime.code_analyzer import CallGraphBuilder
        builder = CallGraphBuilder()
        graph = builder.build_graph(source_dir)
        impacted = builder.impact_analysis(changed_files, graph)
        impacted_files = list(impacted.keys()) if isinstance(impacted, dict) else list(impacted)
        all_changed = list(set(changed_files + impacted_files))
        return select_tests(all_changed, test_dir)
    except Exception:
        return select_tests(changed_files, test_dir)
