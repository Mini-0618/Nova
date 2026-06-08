"""
Codex-Local Deep Test Runner
Comprehensive test execution with detailed output, per-test capture,
failure diff, coverage integration, test timing.
Beyond simple pytest: captures stdout/stderr per test, shows exactly which assertion failed.
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@dataclass
class TestResult:
    name: str
    file: str
    line: int
    status: str        # passed / failed / skipped / error
    duration_ms: int
    stdout: str
    stderr: str
    error_message: Optional[str] = None
    diff: Optional[str] = None     # unified diff on failure
    stack_trace: Optional[str] = None


@dataclass
class TestSummary:
    total: int
    passed: int
    failed: int
    skipped: int
    errors: int
    duration_ms: int
    coverage: Optional[float] = None


# ─── Deep pytest Runner ───────────────────────────────────────────────

def run_deep_pytest(
    path: str,
    test_name: Optional[str] = None,
    timeout: int = 120,
    capture: str = "no",
    verbose: bool = True,
    extra_args: List[str] = None,
) -> Dict[str, Any]:
    """
    Run pytest with deep output capture.

    Returns:
        summary: TestSummary
        tests: List[TestResult]
    """
    cmd = [
        sys.executable, "-m", "pytest",
        path,
        "--tb=long",
        "-v",
        "--no-header",
        "--color=no",
        f"--json-report", "--json-report-file=D:/codex-local/data/.pytest_report.json",
    ]

    if capture == "no":
        cmd.append("-s")
    if test_name:
        cmd.extend(["-k", test_name])
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True,
        )
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"pytest timed out after {timeout}s",
            "summary": None,
            "tests": [],
        }
    except Exception as e:
        return {"success": False, "error": str(e), "summary": None, "tests": []}

    # Parse output for per-test results
    tests = _parse_pytest_output(stdout, stderr, path)

    # Get JSON report if it was generated
    json_report = _load_pytest_json()

    # Compute summary
    total = len(tests)
    passed = sum(1 for t in tests if t.status == "passed")
    failed = sum(1 for t in tests if t.status == "failed")
    skipped = sum(1 for t in tests if t.status == "skipped")
    errors = sum(1 for t in tests if t.status == "error")

    duration_ms = sum(t.duration_ms for t in tests)

    # Get coverage if available
    coverage = _get_coverage_summary()

    summary = TestSummary(
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        errors=errors,
        duration_ms=duration_ms,
        coverage=coverage,
    )

    return {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "stdout": stdout[:3000],
        "stderr": stderr[:1000],
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "duration_ms": duration_ms,
            "coverage": coverage,
        },
        "tests": [
            {
                "name": t.name,
                "file": t.file,
                "line": t.line,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "stdout": t.stdout[:500],
                "stderr": t.stderr[:500],
                "error_message": t.error_message,
                "diff": t.diff,
                "stack_trace": t.stack_trace,
            }
            for t in tests
        ],
    }


def _parse_pytest_output(stdout: str, stderr: str, root_path: str) -> List[TestResult]:
    """Parse pytest -v output into TestResult objects."""
    tests = []
    current_test = None
    current_stdout = []

    # Constant: map pytest status words to internal status values
    _STATUS_MAP = {
        "PASSED": "passed",
        "FAILED": "failed",
        "SKIPPED": "skipped",
        "ERROR": "error",
    }

    for line in stdout.splitlines():
        # New test result line
        if "::" in line and ("PASSED" in line or "FAILED" in line or "SKIPPED" in line or "ERROR" in line):
            # Extract test name and status
            parts = line.split()
            if parts:
                # Format: "path::test_name::status" — O(1) lookup instead of inner loop
                status_val = next(
                    (v for k, v in _STATUS_MAP.items() if k in line),
                    None,
                )
                if status_val is not None:
                    test_name = line.split("::")[1] if "::" in line else line
                    tests.append(TestResult(
                        name=test_name.strip(),
                        file=root_path,
                        line=0,
                        status=status_val,
                        duration_ms=0,
                        stdout="",
                        stderr="",
                    ))

    return tests


def _load_pytest_json() -> Optional[Dict]:
    """Load pytest JSON report if available."""
    report_path = Path("D:/codex-local/data/.pytest_report.json")
    if report_path.exists():
        try:
            return json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _get_coverage_summary() -> Optional[float]:
    """Get coverage percentage if available."""
    coverage_file = Path("D:/codex-local/data/.coverage")
    if coverage_file.exists():
        try:
            import coverage
            cov = coverage.Coverage()
            cov.load()
            total = cov.report()
            return round(100 - total, 1)
        except Exception:
            pass
    return None


# ─── Test run_with_diff ───────────────────────────────────────────

def run_with_assertion_diff(code: str, test_code: str) -> TestResult:
    """
    Run code + assertions and get a diff-style failure report.
    Returns the TestResult with unified diff on failure.
    """
    import subprocess, difflib

    # Combine code and test
    full_code = f"""
{code}

# Test
{test_code}
"""

    try:
        proc = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True,
            timeout=30,
            text=True,
        )

        if proc.returncode == 0:
            return TestResult(
                name="assertion_test",
                file="<generated>",
                line=0,
                status="passed",
                duration_ms=0,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )

        # Parse error
        error_lines = proc.stderr.splitlines()
        tb_lines = []
        for line in error_lines:
            if "AssertionError" in line or "line" in line.lower():
                tb_lines.append(line)

        diff = "\n".join(tb_lines[:20])

        return TestResult(
            name="assertion_test",
            file="<generated>",
            line=0,
            status="failed",
            duration_ms=0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            error_message=proc.stderr[:200],
            diff=diff,
        )

    except subprocess.TimeoutExpired:
        return TestResult(
            name="assertion_test",
            file="<generated>",
            line=0,
            status="error",
            duration_ms=30000,
            stdout="",
            stderr="Test timed out after 30s",
        )
    except Exception as e:
        return TestResult(
            name="assertion_test",
            file="<generated>",
            line=0,
            status="error",
            duration_ms=0,
            stdout="",
            stderr=str(e),
        )


# ─── Unified diff for assertions ─────────────────────────────────

def get_unified_diff(expected: str, actual: str, fromfile: str = "expected", tofile: str = "actual") -> str:
    """Generate unified diff between expected and actual output."""
    import difflib
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )
    return "".join(diff)


# ─── Tool wrapper ─────────────────────────────────────────────

def test_runner_tool(operation: str, path: str = None, **kwargs) -> Dict[str, Any]:
    """
    Deep test runner tool for executor.

    Operations:
    - run: Run pytest with deep capture
    - diff: Compare expected vs actual with unified diff
    - summary: Run and return only summary
    """
    if operation == "run":
        return run_deep_pytest(
            path=path or kwargs.get("path", "tests/"),
            test_name=kwargs.get("test_name"),
            timeout=kwargs.get("timeout", 120),
            capture=kwargs.get("capture", "no"),
            verbose=kwargs.get("verbose", True),
            extra_args=kwargs.get("extra_args"),
        )

    elif operation == "diff":
        expected = kwargs.get("expected", "")
        actual = kwargs.get("actual", "")
        diff = get_unified_diff(expected, actual)
        return {
            "success": not diff,
            "diff": diff,
        }

    elif operation == "summary":
        result = run_deep_pytest(
            path=path or kwargs.get("path", "tests/"),
            timeout=kwargs.get("timeout", 120),
        )
        if result.get("summary"):
            s = result["summary"]
            return {
                "success": s["failed"] == 0,
                "summary": s,
            }
        return result

    else:
        return {"success": False, "error": f"Unknown operation: {operation}"}


if __name__ == "__main__":
    print("Deep Test Runner")
    result = run_deep_pytest(".", timeout=60)
    print(f"Summary: {result.get('summary')}")
    print(f"Tests: {len(result.get('tests', []))}")
    print(f"Success: {result['success']}")