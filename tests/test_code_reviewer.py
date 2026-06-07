"""Tests for runtime/code_reviewer.py — CodeReviewer class."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.code_reviewer import CodeReviewer, ReviewResult, Issue, Severity


def _make_tmp_file(code: str, name: str = "test_file.py") -> str:
    """Write code to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, prefix=name)
    tmp.write(code)
    tmp.close()
    return tmp.name


def test_review_file_clean():
    """A clean file should score 100 with no critical issues."""
    code = '''"""Module docstring."""

import os
from pathlib import Path


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}"


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        assert result.score == 100, f"Expected 100, got {result.score}"
        assert result.critical_count == 0
    finally:
        os.unlink(path)


def test_review_file_eval():
    """eval() usage should be flagged as critical."""
    code = '''def unsafe(code: str):
    return eval(code)
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        assert result.critical_count >= 1
        sec_issues = [i for i in result.issues if i.rule == "SEC001"]
        assert len(sec_issues) >= 1
        assert "eval" in sec_issues[0].message.lower()
    finally:
        os.unlink(path)


def test_review_file_exec():
    """exec() usage should be flagged as critical."""
    code = '''def run(code: str):
    exec(code)
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        assert result.critical_count >= 1
    finally:
        os.unlink(path)


def test_review_file_os_system():
    """os.system() should be flagged as critical."""
    code = '''import os
os.system("rm -rf /tmp/test")
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        assert result.critical_count >= 1
        sec3 = [i for i in result.issues if i.rule == "SEC003"]
        assert len(sec3) >= 1
    finally:
        os.unlink(path)


def test_review_file_subprocess_shell_true():
    """subprocess with shell=True should be flagged."""
    code = '''import subprocess
subprocess.run("ls", shell=True)
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        sec2 = [i for i in result.issues if i.rule == "SEC002"]
        assert len(sec2) >= 1
    finally:
        os.unlink(path)


def test_review_file_hardcoded_secret():
    """Hardcoded password should be flagged."""
    code = '''api_key = "sk-1234567890abcdef"
password = "supersecret123"
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        sec6 = [i for i in result.issues if i.rule == "SEC006"]
        assert len(sec6) >= 2
    finally:
        os.unlink(path)


def test_review_file_bare_except():
    """Bare except should be flagged."""
    code = '''try:
    x = 1 / 0
except:
    pass
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        err1 = [i for i in result.issues if i.rule == "ERR001"]
        assert len(err1) >= 1
    finally:
        os.unlink(path)


def test_review_file_long_function():
    """A function >50 lines should be flagged."""
    lines = ["def long_func():"]
    lines.append('    """Docstring."""')
    for i in range(55):
        lines.append(f"    x_{i} = {i}")
    code = "\n".join(lines) + "\n"
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        read1 = [i for i in result.issues if i.rule == "READ001"]
        assert len(read1) >= 1
    finally:
        os.unlink(path)


def test_review_file_many_args():
    """A function with >7 args should be flagged."""
    code = '''def too_many(a, b, c, d, e, f, g, h):
    """Docstring."""
    return a + b + c + d + e + f + g + h
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        read2 = [i for i in result.issues if i.rule == "READ002"]
        assert len(read2) >= 1
    finally:
        os.unlink(path)


def test_review_file_nested_loops():
    """Nested loops should trigger PERF001."""
    code = '''def matrix_mult(a, b):
    result = []
    for row in a:
        for col in b:
            result.append(row * col)
    return result
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        perf1 = [i for i in result.issues if i.rule == "PERF001"]
        assert len(perf1) >= 1
    finally:
        os.unlink(path)


def test_review_file_syntax_error():
    """Syntax error should be caught."""
    code = '''def broken(
    x = 1 +
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        syn = [i for i in result.issues if i.rule == "SYN001"]
        assert len(syn) >= 1
        assert result.score < 100
    finally:
        os.unlink(path)


def test_review_file_not_found():
    """Non-existent file should return error."""
    reviewer = CodeReviewer()
    result = reviewer.review_file("/nonexistent/file.py")
    assert result.score == 0
    assert result.critical_count >= 1


def test_review_file_print_statement():
    """print() statements should be flagged."""
    code = '''def debug():
    print("debugging")
    print(x)
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        pat2 = [i for i in result.issues if i.rule == "PAT002"]
        assert len(pat2) >= 2
    finally:
        os.unlink(path)


def test_review_file_todo_comment():
    """TODO comments should be flagged."""
    code = '''# TODO: implement this properly
def placeholder():
    pass
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        pat1 = [i for i in result.issues if i.rule == "PAT001"]
        assert len(pat1) >= 1
    finally:
        os.unlink(path)


def test_review_diff_basic():
    """Diff review should detect issues in added code."""
    diff = '''--- a/foo.py
+++ b/foo.py
@@ -1,3 +1,5 @@
+import os
+os.system("echo hello")
+password = "secret123"
 def foo():
     pass
'''
    reviewer = CodeReviewer()
    result = reviewer.review_diff(diff)
    assert len(result.issues) >= 2  # os.system + hardcoded password


def test_review_diff_test_removal():
    """Removing tests in a diff should be flagged."""
    diff = '''--- a/test_foo.py
+++ b/test_foo.py
@@ -1,5 +1,2 @@
-def test_addition():
-    assert add(1, 2) == 3
-
 def test_subtraction():
     assert sub(3, 1) == 2
'''
    reviewer = CodeReviewer()
    result = reviewer.review_diff(diff)
    diff2 = [i for i in result.issues if i.rule == "DIFF002"]
    assert len(diff2) >= 1


def test_review_pr_multiple_files():
    """PR review should aggregate issues from multiple files."""
    code1 = 'eval("1+1")\n'
    code2 = 'def clean():\n    return 42\n'
    path1 = _make_tmp_file(code1, "bad_")
    path2 = _make_tmp_file(code2, "good_")
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_pr([path1, path2])
        assert result.critical_count >= 1  # from eval
        assert "PR" in result.file_path
    finally:
        os.unlink(path1)
        os.unlink(path2)


def test_review_result_severity_property():
    """Test severity property logic."""
    # All info -> info
    r = ReviewResult(issues=[Issue(rule="X", severity=Severity.INFO, message="m")])
    assert r.severity == "info"

    # One warning -> warning
    r.issues.append(Issue(rule="X", severity=Severity.WARNING, message="m"))
    assert r.severity == "warning"

    # One critical -> critical
    r.issues.append(Issue(rule="X", severity=Severity.CRITICAL, message="m"))
    assert r.severity == "critical"


def test_review_result_to_dict():
    """Test serialization."""
    r = ReviewResult(
        file_path="test.py",
        issues=[Issue(rule="SEC001", severity=Severity.CRITICAL, message="eval detected", line=5)],
        score=85,
        summary="1 critical issue",
    )
    d = r.to_dict()
    assert d["file_path"] == "test.py"
    assert d["score"] == 85
    assert len(d["issues"]) == 1
    assert d["issues"][0]["rule"] == "SEC001"


def test_review_file_missing_docstring():
    """Functions without docstrings should be flagged."""
    code = '''def undocumented(x):
    return x + 1
'''
    path = _make_tmp_file(code)
    try:
        reviewer = CodeReviewer()
        result = reviewer.review_file(path)
        read3 = [i for i in result.issues if i.rule == "READ003"]
        assert len(read3) >= 1
    finally:
        os.unlink(path)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
