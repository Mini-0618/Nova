"""Tests for runtime.test_selector module."""

import os
import tempfile
from pathlib import Path

from runtime.test_selector import (
    _find_test_files,
    _parse_imports,
    _map_test_to_source,
    _changed_to_modules,
    select_tests,
)


class TestFindTestFiles:
    def test_finds_test_files(self, tmp_path):
        (tmp_path / "test_alpha.py").write_text("pass")
        (tmp_path / "test_beta.py").write_text("pass")
        (tmp_path / "not_test.py").write_text("pass")
        (tmp_path / "test_sub.py").mkdir()
        result = _find_test_files(str(tmp_path))
        names = [p.name for p in result]
        assert "test_alpha.py" in names
        assert "test_beta.py" in names
        assert "not_test.py" not in names

    def test_empty_dir(self, tmp_path):
        result = _find_test_files(str(tmp_path))
        assert result == []

    def test_nonexistent_dir(self):
        result = _find_test_files("/nonexistent/path/xyz")
        assert result == []


class TestParseImports:
    def test_basic_imports(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("import os\nfrom pathlib import Path\nimport json")
        modules = _parse_imports(f)
        assert "os" in modules
        assert "pathlib" in modules
        assert "json" in modules

    def test_syntax_error_returns_empty(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def foo(:\n")
        modules = _parse_imports(f)
        assert modules == set()


class TestMapTestToSource:
    def test_filename_mapping(self, tmp_path):
        f = tmp_path / "test_llm_client.py"
        f.write_text("import pytest")
        sources = _map_test_to_source(f)
        assert "llm_client" in sources

    def test_import_mapping(self, tmp_path):
        f = tmp_path / "test_custom.py"
        f.write_text("from runtime.my_module import Foo")
        sources = _map_test_to_source(f)
        assert "my_module" in sources or "runtime" in sources


class TestChangedToModules:
    def test_basic(self):
        modules = _changed_to_modules(["runtime/code_analyzer.py", "runtime/llm_client.py"])
        assert "code_analyzer" in modules
        assert "llm_client" in modules
        assert "runtime" in modules

    def test_non_python_ignored(self):
        modules = _changed_to_modules(["README.md", "Makefile"])
        assert len(modules) == 0


class TestSelectTests:
    def test_matches_changed_module(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text("import pytest\nimport runtime.foo")
        (tests_dir / "test_bar.py").write_text("import pytest\nimport runtime.bar")

        result = select_tests(["runtime/foo.py"], test_dir=str(tests_dir))
        names = [Path(r).name for r in result]
        assert "test_foo.py" in names

    def test_config_change_runs_all(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("pass")
        (tests_dir / "test_b.py").write_text("pass")

        result = select_tests(
            ["pyproject.toml"],
            test_dir=str(tests_dir),
            include_all_on_config_change=True,
        )
        assert len(result) == 2

    def test_fallback_runs_all(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_x.py").write_text("pass")
        (tests_dir / "test_y.py").write_text("pass")

        # No test matches "nonexistent" module, so should fall back to all
        result = select_tests(["nonexistent.py"], test_dir=str(tests_dir))
        assert len(result) == 2
