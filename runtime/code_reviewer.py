"""
Codex-Local Code Reviewer
Static analysis + rule-based code review without LLM dependency.

Usage:
    from runtime.code_reviewer import CodeReviewer
    reviewer = CodeReviewer()
    result = reviewer.review_file("path/to/file.py")
    result = reviewer.review_diff(diff_text)
    result = reviewer.review_pr(["file1.py", "file2.py"])
"""

import ast
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Issue:
    """A single code review issue."""
    rule: str  # e.g. "SEC001", "PERF002"
    severity: Severity
    message: str
    file_path: str = ""
    line: int = 0
    column: int = 0
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "suggestion": self.suggestion,
        }


@dataclass
class ReviewResult:
    """Result of a code review."""
    file_path: str = ""
    issues: List[Issue] = field(default_factory=list)
    score: int = 100  # 0-100, starts perfect, deductions per issue
    summary: str = ""

    @property
    def severity(self) -> str:
        """Overall severity: worst issue found."""
        if any(i.severity == Severity.CRITICAL for i in self.issues):
            return "critical"
        if any(i.severity == Severity.WARNING for i in self.issues):
            return "warning"
        return "info"

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.INFO)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "score": self.score,
            "severity": self.severity,
            "summary": self.summary,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "issues": [i.to_dict() for i in self.issues],
        }


class CodeReviewer:
    """Rule-based code reviewer using AST analysis and pattern matching."""

    # Deduction points per severity
    DEDUCTION = {
        Severity.CRITICAL: 15,
        Severity.WARNING: 5,
        Severity.INFO: 1,
    }

    # ─── Public API ────────────────────────────────────────────────────

    def review_file(self, file_path: str) -> ReviewResult:
        """Review a single Python file."""
        path = Path(file_path)
        if not path.exists():
            return ReviewResult(
                file_path=file_path,
                issues=[Issue(
                    rule="FILE001",
                    severity=Severity.CRITICAL,
                    message=f"File not found: {file_path}",
                )],
                score=0,
                summary="File not found",
            )

        if path.suffix != ".py":
            return ReviewResult(
                file_path=file_path,
                issues=[Issue(
                    rule="FILE002",
                    severity=Severity.INFO,
                    message=f"Non-Python file, only pattern checks applied",
                )],
                score=100,
                summary="Non-Python file reviewed with limited checks",
            )

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ReviewResult(
                file_path=file_path,
                issues=[Issue(
                    rule="FILE003",
                    severity=Severity.CRITICAL,
                    message=f"Cannot read file: {e}",
                )],
                score=0,
                summary="File unreadable",
            )

        issues: List[Issue] = []

        # AST-based checks
        try:
            tree = ast.parse(content, filename=file_path)
            issues.extend(self._check_security(tree, file_path))
            issues.extend(self._check_performance(tree, file_path))
            issues.extend(self._check_readability(tree, file_path, content))
            issues.extend(self._check_error_handling(tree, file_path))
            issues.extend(self._check_testing(tree, file_path, content))
        except SyntaxError as e:
            issues.append(Issue(
                rule="SYN001",
                severity=Severity.CRITICAL,
                message=f"Syntax error: {e.msg}",
                file_path=file_path,
                line=e.lineno or 0,
                column=e.offset or 0,
            ))

        # Pattern-based checks (work even with syntax errors)
        issues.extend(self._check_patterns(content, file_path))

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score)

        return ReviewResult(
            file_path=file_path,
            issues=issues,
            score=score,
            summary=summary,
        )

    def review_diff(self, diff_text: str) -> ReviewResult:
        """Review a unified diff for quality issues."""
        issues: List[Issue] = []

        added_lines = []
        removed_lines = []
        current_file = ""

        for line in diff_text.splitlines():
            # Track which file we're in
            if line.startswith("+++ b/"):
                current_file = line[6:]
            elif line.startswith("--- a/"):
                pass

            # Collect added/removed lines
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append((current_file, line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines.append((current_file, line[1:]))

        # Check diff-level issues
        issues.extend(self._check_diff_quality(diff_text, added_lines, removed_lines))

        # Check added code for security issues
        for file_path, line in added_lines:
            issues.extend(self._check_line_security(line, file_path))
            issues.extend(self._check_line_patterns(line, file_path))

        score = self._calculate_score(issues)
        summary = self._build_summary(issues, score)

        return ReviewResult(
            file_path="(diff)",
            issues=issues,
            score=score,
            summary=summary,
        )

    def review_pr(self, changed_files: List[str]) -> ReviewResult:
        """Review a set of changed files (PR-level review)."""
        all_issues: List[Issue] = []
        file_results: List[ReviewResult] = []

        for file_path in changed_files:
            result = self.review_file(file_path)
            file_results.append(result)
            all_issues.extend(result.issues)

        # Cross-file checks
        all_issues.extend(self._check_cross_file(file_results))

        score = self._calculate_score(all_issues)
        summary = self._build_summary(all_issues, score, pr_level=True)

        return ReviewResult(
            file_path=f"PR ({len(changed_files)} files)",
            issues=all_issues,
            score=score,
            summary=summary,
        )

    # ─── Security Checks (AST-based) ──────────────────────────────────

    def _check_security(self, tree: ast.AST, file_path: str) -> List[Issue]:
        issues = []
        for node in ast.walk(tree):
            # eval() / exec() calls
            if isinstance(node, ast.Call):
                func_name = self._get_call_name(node)
                if func_name in ("eval", "exec"):
                    issues.append(Issue(
                        rule="SEC001",
                        severity=Severity.CRITICAL,
                        message=f"Dangerous use of {func_name}()",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion=f"Avoid {func_name}(). Use ast.literal_eval() for eval, or refactor exec to specific function calls.",
                    ))

                # subprocess with shell=True
                if func_name in ("subprocess.call", "subprocess.run", "subprocess.Popen",
                                 "subprocess.check_output", "subprocess.check_call"):
                    for kw in node.keywords:
                        if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            issues.append(Issue(
                                rule="SEC002",
                                severity=Severity.WARNING,
                                message="subprocess with shell=True — potential shell injection",
                                file_path=file_path,
                                line=getattr(node, "lineno", 0),
                                suggestion="Use shell=False with a list of args instead.",
                            ))

                # os.system()
                if func_name == "os.system":
                    issues.append(Issue(
                        rule="SEC003",
                        severity=Severity.CRITICAL,
                        message="os.system() is vulnerable to shell injection",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Use subprocess.run() with shell=False instead.",
                    ))

                # pickle.loads without restriction
                if func_name in ("pickle.loads", "pickle.load", "yaml.load"):
                    issues.append(Issue(
                        rule="SEC004",
                        severity=Severity.WARNING,
                        message=f"{func_name}() can execute arbitrary code during deserialization",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Use yaml.safe_load() or restrict pickle sources.",
                    ))

                # hashlib.md5 / hashlib.sha1 (weak hash)
                if func_name in ("hashlib.md5", "hashlib.sha1"):
                    issues.append(Issue(
                        rule="SEC005",
                        severity=Severity.INFO,
                        message=f"Weak hash function: {func_name}",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Use hashlib.sha256() or stronger for security-sensitive hashing.",
                    ))

            # Hardcoded secrets
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id.lower()
                        if any(kw in name for kw in ("password", "secret", "token", "api_key", "apikey")):
                            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                                if len(node.value.value) > 3:
                                    issues.append(Issue(
                                        rule="SEC006",
                                        severity=Severity.WARNING,
                                        message=f"Possible hardcoded secret in variable '{target.id}'",
                                        file_path=file_path,
                                        line=getattr(node, "lineno", 0),
                                        suggestion="Use environment variables or a secrets manager.",
                                    ))

        return issues

    # ─── Performance Checks (AST-based) ───────────────────────────────

    def _check_performance(self, tree: ast.AST, file_path: str) -> List[Issue]:
        issues = []
        for node in ast.walk(tree):
            # Nested loops (O(n^2) pattern)
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if child is not node and isinstance(child, (ast.For, ast.While)):
                        issues.append(Issue(
                            rule="PERF001",
                            severity=Severity.WARNING,
                            message="Nested loop detected — potential O(n^2) complexity",
                            file_path=file_path,
                            line=getattr(node, "lineno", 0),
                            suggestion="Consider using a dict/set lookup or itertools to reduce complexity.",
                        ))
                        break  # Only flag once per outer loop

            # String concatenation in loop
            if isinstance(node, (ast.For, ast.While)):
                for child in ast.walk(node):
                    if isinstance(child, ast.AugAssign) and isinstance(child.op, ast.Add):
                        if isinstance(child.target, ast.Name):
                            issues.append(Issue(
                                rule="PERF002",
                                severity=Severity.INFO,
                                message="String concatenation in loop — consider join() or list append",
                                file_path=file_path,
                                line=getattr(child, "lineno", 0),
                                suggestion="Collect items in a list, then use ''.join(list) after the loop.",
                            ))

            # Global import inside function
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        issues.append(Issue(
                            rule="PERF003",
                            severity=Severity.INFO,
                            message=f"Import inside function '{node.name}' — adds overhead on each call",
                            file_path=file_path,
                            line=getattr(child, "lineno", 0),
                            suggestion="Move the import to the top of the file unless it's intentionally deferred.",
                        ))

        return issues

    # ─── Readability Checks (AST-based) ───────────────────────────────

    def _check_readability(self, tree: ast.AST, file_path: str, content: str) -> List[Issue]:
        issues = []
        lines = content.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Function too long (>50 lines)
                func_lines = self._count_node_lines(node)
                if func_lines > 50:
                    issues.append(Issue(
                        rule="READ001",
                        severity=Severity.WARNING,
                        message=f"Function '{node.name}' is {func_lines} lines long (>50)",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Break into smaller functions (aim for <30 lines).",
                    ))

                # Too many arguments (>7)
                args = node.args
                total_args = len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs)
                if args.vararg:
                    total_args += 1
                if args.kwarg:
                    total_args += 1
                if total_args > 7:
                    issues.append(Issue(
                        rule="READ002",
                        severity=Severity.WARNING,
                        message=f"Function '{node.name}' has {total_args} parameters (>7)",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Use a dataclass or config object to group related parameters.",
                    ))

                # Missing docstring
                if not ast.get_docstring(node):
                    issues.append(Issue(
                        rule="READ003",
                        severity=Severity.INFO,
                        message=f"Function '{node.name}' has no docstring",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Add a one-line docstring describing what the function does.",
                    ))

            # Class too long
            if isinstance(node, ast.ClassDef):
                class_lines = self._count_node_lines(node)
                if class_lines > 200:
                    issues.append(Issue(
                        rule="READ004",
                        severity=Severity.WARNING,
                        message=f"Class '{node.name}' is {class_lines} lines long (>200)",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Consider splitting into smaller classes or using composition.",
                    ))

                if not ast.get_docstring(node):
                    issues.append(Issue(
                        rule="READ005",
                        severity=Severity.INFO,
                        message=f"Class '{node.name}' has no docstring",
                        file_path=file_path,
                        line=getattr(node, "lineno", 0),
                        suggestion="Add a class docstring.",
                    ))

        # Line length check (>120 chars)
        for i, line in enumerate(lines, 1):
            if len(line) > 120 and not line.strip().startswith("#"):
                issues.append(Issue(
                    rule="READ006",
                    severity=Severity.INFO,
                    message=f"Line {i} is {len(line)} characters (>120)",
                    file_path=file_path,
                    line=i,
                    suggestion="Break the line or use intermediate variables.",
                ))

        return issues

    # ─── Error Handling Checks (AST-based) ────────────────────────────

    def _check_error_handling(self, tree: ast.AST, file_path: str) -> List[Issue]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for handler in node.handlers:
                    # Bare except
                    if handler.type is None:
                        issues.append(Issue(
                            rule="ERR001",
                            severity=Severity.WARNING,
                            message="Bare 'except:' catches all exceptions including KeyboardInterrupt",
                            file_path=file_path,
                            line=getattr(handler, "lineno", 0),
                            suggestion="Use 'except Exception:' at minimum, or catch specific exceptions.",
                        ))

                    # except with pass (silenced errors)
                    if (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)):
                        issues.append(Issue(
                            rule="ERR002",
                            severity=Severity.WARNING,
                            message="Exception silently swallowed with 'except: pass'",
                            file_path=file_path,
                            line=getattr(handler, "lineno", 0),
                            suggestion="At minimum, log the exception or add a comment explaining why it's safe to ignore.",
                        ))

                    # except Exception as e: pass (swallowed with unused variable)
                    if (handler.name and len(handler.body) == 1
                            and isinstance(handler.body[0], ast.Pass)):
                        issues.append(Issue(
                            rule="ERR003",
                            severity=Severity.WARNING,
                            message=f"Exception '{handler.name}' caught but ignored",
                            file_path=file_path,
                            line=getattr(handler, "lineno", 0),
                            suggestion="Use the exception variable (e.g., logging) or remove the 'as' clause.",
                        ))

        return issues

    # ─── Testing Checks ───────────────────────────────────────────────

    def _check_testing(self, tree: ast.AST, file_path: str, content: str) -> List[Issue]:
        issues = []

        # Skip test files themselves
        basename = os.path.basename(file_path)
        if basename.startswith("test_") or basename.endswith("_test.py"):
            return issues

        # Check if file has corresponding test
        dir_path = os.path.dirname(file_path)
        test_candidates = [
            os.path.join(dir_path, "tests", f"test_{basename}"),
            os.path.join(dir_path, "test", f"test_{basename}"),
            os.path.join(dir_path, f"test_{basename}"),
        ]

        has_test = any(os.path.exists(p) for p in test_candidates)

        # Count public functions/classes
        public_items = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    public_items.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    public_items.append(node.name)

        if public_items and not has_test:
            issues.append(Issue(
                rule="TEST001",
                severity=Severity.INFO,
                message=f"No test file found for {basename} (has {len(public_items)} public items)",
                file_path=file_path,
                line=0,
                suggestion=f"Create tests/test_{basename} with tests for: {', '.join(public_items[:5])}",
            ))

        return issues

    # ─── Pattern-based Checks ─────────────────────────────────────────

    def _check_patterns(self, content: str, file_path: str) -> List[Issue]:
        issues = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # TODO/FIXME/HACK comments
            if re.search(r'\b(TODO|FIXME|HACK|XXX)\b', stripped, re.IGNORECASE):
                issues.append(Issue(
                    rule="PAT001",
                    severity=Severity.INFO,
                    message=f"Unresolved TODO/FIXME/HACK comment",
                    file_path=file_path,
                    line=i,
                    suggestion="Address the TODO or create a tracking issue.",
                ))

            # print() statements (debugging leftovers)
            if re.match(r'^\s*print\(', stripped) and not stripped.startswith('#'):
                issues.append(Issue(
                    rule="PAT002",
                    severity=Severity.INFO,
                    message="print() statement — consider using logging",
                    file_path=file_path,
                    line=i,
                    suggestion="Replace with logging.info() or logging.debug().",
                ))

            # type: ignore without explanation
            if 'type: ignore' in line and '#' not in line.split('type: ignore')[0]:
                issues.append(Issue(
                    rule="PAT003",
                    severity=Severity.INFO,
                    message="type: ignore without explanation",
                    file_path=file_path,
                    line=i,
                    suggestion="Add a comment explaining why the type check is suppressed.",
                ))

        return issues

    def _check_line_security(self, line: str, file_path: str) -> List[Issue]:
        """Check a single line for security patterns (for diff review)."""
        issues = []
        stripped = line.strip()

        if re.search(r'\beval\s*\(', stripped):
            issues.append(Issue(
                rule="SEC001",
                severity=Severity.CRITICAL,
                message="eval() detected in added code",
                file_path=file_path,
                suggestion="Avoid eval(). Use ast.literal_eval() or a specific parser.",
            ))

        if re.search(r'\bexec\s*\(', stripped):
            issues.append(Issue(
                rule="SEC001",
                severity=Severity.CRITICAL,
                message="exec() detected in added code",
                file_path=file_path,
                suggestion="Avoid exec(). Refactor to use specific function calls.",
            ))

        if 'os.system(' in stripped:
            issues.append(Issue(
                rule="SEC003",
                severity=Severity.CRITICAL,
                message="os.system() in added code — shell injection risk",
                file_path=file_path,
                suggestion="Use subprocess.run() with shell=False.",
            ))

        return issues

    def _check_line_patterns(self, line: str, file_path: str) -> List[Issue]:
        """Check a single line for general patterns (for diff review)."""
        issues = []

        if re.search(r'\bpassword\s*=\s*["\']', line, re.IGNORECASE):
            issues.append(Issue(
                rule="SEC006",
                severity=Severity.WARNING,
                message="Hardcoded password in added code",
                file_path=file_path,
                suggestion="Use environment variables for credentials.",
            ))

        return issues

    def _check_diff_quality(self, diff_text: str,
                            added: List[Tuple[str, str]],
                            removed: List[Tuple[str, str]]) -> List[Issue]:
        """Check diff-level quality issues."""
        issues = []

        # Very large diff
        total_changes = len(added) + len(removed)
        if total_changes > 500:
            issues.append(Issue(
                rule="DIFF001",
                severity=Severity.WARNING,
                message=f"Very large diff: {total_changes} lines changed",
                suggestion="Consider splitting into smaller, focused changes.",
            ))

        # Check if tests were removed
        for file_path, line in removed:
            if 'test' in file_path.lower() or 'assert' in line.lower():
                if re.search(r'\b(def test_|assert )\b', line):
                    issues.append(Issue(
                        rule="DIFF002",
                        severity=Severity.WARNING,
                        message="Test code or assertion was removed",
                        file_path=file_path,
                        suggestion="Removing tests weakens quality guarantees.",
                    ))

        return issues

    def _check_cross_file(self, results: List[ReviewResult]) -> List[Issue]:
        """Cross-file analysis for PR-level review."""
        issues = []

        # Check if any critical issues exist
        critical_files = [r.file_path for r in results if r.critical_count > 0]
        if critical_files:
            issues.append(Issue(
                rule="PR001",
                severity=Severity.CRITICAL,
                message=f"Critical issues found in: {', '.join(critical_files[:5])}",
                suggestion="Fix all critical issues before merging.",
            ))

        # Low average score
        if results:
            avg_score = sum(r.score for r in results) / len(results)
            if avg_score < 60:
                issues.append(Issue(
                    rule="PR002",
                    severity=Severity.WARNING,
                    message=f"Average code quality score is low: {avg_score:.0f}/100",
                    suggestion="Review and fix warnings before merging.",
                ))

        return issues

    # ─── Helpers ───────────────────────────────────────────────────────

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract the full function name from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""

    def _count_node_lines(self, node: ast.AST) -> int:
        """Count the number of lines in an AST node."""
        if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
            if node.end_lineno and node.lineno:
                return node.end_lineno - node.lineno + 1
        return 0

    def _calculate_score(self, issues: List[Issue]) -> int:
        """Calculate quality score from issues (starts at 100)."""
        score = 100
        for issue in issues:
            score -= self.DEDUCTION.get(issue.severity, 1)
        return max(0, score)

    def _build_summary(self, issues: List[Issue], score: int,
                       pr_level: bool = False) -> str:
        """Build a human-readable summary."""
        if not issues:
            return "No issues found. Code looks good!"

        parts = [f"Score: {score}/100"]
        if any(i.severity == Severity.CRITICAL for i in issues):
            parts.append("CRITICAL issues found — must fix before merging")
        elif any(i.severity == Severity.WARNING for i in issues):
            parts.append("Warnings found — review recommended")

        counts = {}
        for issue in issues:
            counts[issue.severity.value] = counts.get(issue.severity.value, 0) + 1

        count_parts = []
        for sev in ("critical", "warning", "info"):
            if sev in counts:
                count_parts.append(f"{counts[sev]} {sev}")
        parts.append(", ".join(count_parts))

        return " | ".join(parts)
