"""
Test CallGraphBuilder - code analysis and impact analysis.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.code_analyzer import CallGraphBuilder

FIXTURES = str(Path(__file__).parent / "fixtures" / "sample_project")


def test_build_graph():
    """Test that build_graph finds functions and calls."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    assert isinstance(graph, dict)
    assert len(graph) > 0, "Should find at least one function"

    # Check that some known functions are present
    all_funcs = list(graph.keys())
    func_names = [f.split(".")[-1] for f in all_funcs]
    assert "helper_a" in func_names
    assert "helper_b" in func_names
    assert "helper_c" in func_names
    assert "process_data" in func_names
    assert "main" in func_names
    print(f"  [OK] Found {len(graph)} functions")


def test_find_callees():
    """Test finding what a function calls."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    # helper_b should call helper_a
    callees = builder.find_callees("helper_b", graph)
    callee_names = [c.split(".")[-1] for c in callees]
    assert "helper_a" in callee_names, f"helper_b should call helper_a, got {callees}"
    print(f"  [OK] helper_b calls: {callees}")


def test_find_callees_complex():
    """Test finding callees of a function with multiple calls."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    # helper_c should call helper_a and helper_b
    callees = builder.find_callees("helper_c", graph)
    callee_names = [c.split(".")[-1] for c in callees]
    assert "helper_a" in callee_names, f"helper_c should call helper_a, got {callees}"
    assert "helper_b" in callee_names, f"helper_c should call helper_b, got {callees}"
    print(f"  [OK] helper_c calls: {callees}")


def test_find_callers():
    """Test finding who calls a function."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    # helper_a is called by helper_b and helper_c
    callers = builder.find_callers("helper_a", graph)
    assert len(callers) >= 2, f"helper_a should have >=2 callers, got {callers}"
    caller_names = [c.split(".")[-1] for c in callers]
    assert "helper_b" in caller_names
    assert "helper_c" in caller_names
    print(f"  [OK] helper_a callers: {callers}")


def test_find_callers_no_match():
    """Test finding callers of a nonexistent function."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    callers = builder.find_callers("nonexistent_function", graph)
    assert callers == [], f"Should return empty for nonexistent function, got {callers}"
    print(f"  [OK] No callers for nonexistent function")


def test_impact_analysis():
    """Test impact analysis when a file changes."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    # Find the utils.py file path
    utils_path = os.path.join(FIXTURES, "utils.py")
    assert os.path.exists(utils_path)

    impacted = builder.impact_analysis([utils_path], graph)
    # core.py depends on utils, so it should be impacted
    impacted_names = [os.path.basename(f) for f in impacted]
    assert "core.py" in impacted_names, f"core.py should be impacted by utils.py change, got {impacted}"
    print(f"  [OK] Changing utils.py impacts: {impacted}")


def test_impact_analysis_no_impact():
    """Test impact analysis for a leaf file with no dependents."""
    builder = CallGraphBuilder()
    graph = builder.build_graph(FIXTURES)

    # core.py is not called by anything in the sample
    core_path = os.path.join(FIXTURES, "core.py")
    impacted = builder.impact_analysis([core_path], graph)
    # Should be empty or only external
    print(f"  [OK] Changing core.py impacts: {impacted}")


def test_empty_directory():
    """Test building graph for an empty directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        builder = CallGraphBuilder()
        graph = builder.build_graph(tmpdir)
        assert graph == {}
    print(f"  [OK] Empty directory returns empty graph")


def test_syntax_error_file():
    """Test that files with syntax errors are skipped gracefully."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a valid file
        with open(os.path.join(tmpdir, "good.py"), "w") as f:
            f.write("def ok():\n    return 1\n")
        # Create a bad file
        with open(os.path.join(tmpdir, "bad.py"), "w") as f:
            f.write("def broken(\n")

        builder = CallGraphBuilder()
        graph = builder.build_graph(tmpdir)
        assert len(graph) >= 1, "Should find at least the good function"
    print(f"  [OK] Syntax errors skipped gracefully")


def main():
    """Run all tests."""
    tests = [
        ("Build Graph", test_build_graph),
        ("Find Callees", test_find_callees),
        ("Find Callees Complex", test_find_callees_complex),
        ("Find Callers", test_find_callers),
        ("Find Callers No Match", test_find_callers_no_match),
        ("Impact Analysis", test_impact_analysis),
        ("Impact Analysis No Impact", test_impact_analysis_no_impact),
        ("Empty Directory", test_empty_directory),
        ("Syntax Error File", test_syntax_error_file),
    ]

    print("=" * 60)
    print("CODE ANALYZER TEST SUITE")
    print("=" * 60)

    passed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")

    print(f"\n  {passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
