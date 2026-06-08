"""
代码质量检查器：AST 分析 + 文本模式检测 + 圈复杂度

用法：
    python skills/quality_guard.py coding_tools.py
    python skills/quality_guard.py coding_tools.py --out quality_report.md
    python skills/quality_guard.py coding_tools.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class Issue:
    level: str
    code: str
    line: int
    message: str
    suggestion: str


@dataclass
class QualityReport:
    file: str
    score: int
    total_issues: int
    critical: int
    high: int
    medium: int
    low: int
    issues: list[Issue]


class QualityGuard(ast.NodeVisitor):
    def __init__(self, source: str, filename: str) -> None:
        self.source = source
        self.filename = filename
        self.lines = source.splitlines()
        self.issues: list[Issue] = []

    def add(
        self,
        level: str,
        code: str,
        line: int,
        message: str,
        suggestion: str,
    ) -> None:
        self.issues.append(
            Issue(
                level=level,
                code=code,
                line=line,
                message=message,
                suggestion=suggestion,
            )
        )

    def check(self) -> QualityReport:
        try:
            tree = ast.parse(self.source)
        except SyntaxError as exc:
            self.add(
                "CRITICAL",
                "SYNTAX_ERROR",
                exc.lineno or 1,
                f"语法错误：{exc.msg}",
                "先修复语法错误，否则无法继续做质量分析。",
            )
            return self.build_report()

        if not ast.get_docstring(tree):
            self.add(
                "LOW",
                "MISSING_MODULE_DOCSTRING",
                1,
                "模块缺少说明文档。",
                "在文件开头添加模块 docstring，说明这个文件的用途。",
            )

        self.visit(tree)
        self.check_text_patterns()
        self.check_duplicate_lines()
        return self.build_report()

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        if not node.name.startswith("_") and not ast.get_docstring(node):
            self.add(
                "LOW",
                "MISSING_CLASS_DOCSTRING",
                node.lineno,
                f"类 {node.name} 缺少 docstring。",
                "给公共类添加 docstring，说明职责、输入输出和边界。",
            )

        if len(node.body) > 30:
            self.add(
                "MEDIUM",
                "LARGE_CLASS",
                node.lineno,
                f"类 {node.name} 过长，包含 {len(node.body)} 个成员。",
                "考虑拆分职责，把工具函数、状态管理、执行逻辑分开。",
            )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.check_function(node)
        self.generic_visit(node)

    def check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        start = node.lineno
        end = getattr(node, "end_lineno", node.lineno)
        length = end - start + 1

        if length > 60:
            self.add(
                "MEDIUM",
                "LONG_FUNCTION",
                node.lineno,
                f"函数 {node.name} 太长，共 {length} 行。",
                "拆分为多个小函数，每个函数只做一件事。",
            )

        if not node.name.startswith("_") and not ast.get_docstring(node):
            self.add(
                "LOW",
                "MISSING_FUNCTION_DOCSTRING",
                node.lineno,
                f"函数 {node.name} 缺少 docstring。",
                "给公共函数添加 docstring，说明参数、返回值和异常。",
            )

        args = node.args.args + node.args.kwonlyargs

        normal_args = [
            arg for arg in args
            if arg.arg not in ("self", "cls")
        ]

        if len(normal_args) > 6:
            self.add(
                "MEDIUM",
                "TOO_MANY_ARGUMENTS",
                node.lineno,
                f"函数 {node.name} 参数过多，共 {len(normal_args)} 个。",
                "考虑使用配置对象、dataclass 或拆分函数。",
            )

        for arg in normal_args:
            if arg.annotation is None:
                self.add(
                    "LOW",
                    "MISSING_ARG_TYPE",
                    node.lineno,
                    f"函数 {node.name} 的参数 {arg.arg} 缺少类型提示。",
                    "给参数添加类型提示。",
                )

        if node.returns is None and node.name != "__init__":
            self.add(
                "LOW",
                "MISSING_RETURN_TYPE",
                node.lineno,
                f"函数 {node.name} 缺少返回类型提示。",
                "添加 -> None 或具体返回类型。",
            )

        complexity = self.calculate_complexity(node)

        if complexity > 10:
            self.add(
                "HIGH",
                "HIGH_COMPLEXITY",
                node.lineno,
                f"函数 {node.name} 圈复杂度偏高：{complexity}。",
                "减少 if/for/while/try 嵌套，拆分判断逻辑。",
            )
        elif complexity > 6:
            self.add(
                "MEDIUM",
                "MEDIUM_COMPLEXITY",
                node.lineno,
                f"函数 {node.name} 圈复杂度较高：{complexity}。",
                "可以考虑拆分分支逻辑。",
            )

    def calculate_complexity(self, node: ast.AST) -> int:
        complexity = 1

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While)):
                complexity += 1
            elif isinstance(child, ast.Try):
                complexity += len(child.handlers)
            elif isinstance(child, ast.BoolOp):
                complexity += max(1, len(child.values) - 1)
            elif isinstance(child, ast.IfExp):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1

        return complexity

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> Any:
        if node.type is None:
            self.add(
                "HIGH",
                "BARE_EXCEPT",
                node.lineno,
                "发现裸 except。",
                "改成 except SpecificError，避免吞掉 KeyboardInterrupt/SystemExit。",
            )

        elif isinstance(node.type, ast.Name):
            if node.type.id in ("Exception", "BaseException"):
                self.add(
                    "MEDIUM",
                    "BROAD_EXCEPT",
                    node.lineno,
                    f"捕获范围过宽：{node.type.id}。",
                    "尽量捕获具体异常，并记录上下文。",
                )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        call_name = self.get_call_name(node)

        if call_name == "print":
            self.add(
                "LOW",
                "PRINT_USED",
                node.lineno,
                "代码中使用了 print。",
                "库代码建议使用 logging，Demo 代码可以保留。",
            )

        if call_name in ("eval", "exec"):
            self.add(
                "CRITICAL",
                "DANGEROUS_EXECUTION",
                node.lineno,
                f"发现危险调用：{call_name}。",
                "不要对不可信输入使用 eval/exec。",
            )

        if call_name == "os.system":
            self.add(
                "HIGH",
                "OS_SYSTEM",
                node.lineno,
                "发现 os.system 调用。",
                "改用 subprocess.run([...], shell=False)。",
            )

        if call_name.startswith("subprocess."):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                    if kw.value.value is True:
                        self.add(
                            "HIGH",
                            "SUBPROCESS_SHELL_TRUE",
                            node.lineno,
                            "subprocess 使用了 shell=True。",
                            "改成 shell=False，并用 list 传参。",
                        )

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        for alias in node.names:
            if alias.name == "*":
                self.add(
                    "MEDIUM",
                    "WILDCARD_IMPORT",
                    node.lineno,
                    "发现 from xxx import *。",
                    "改成显式导入需要的名称。",
                )

        self.generic_visit(node)

    def get_call_name(self, node: ast.Call) -> str:
        func = node.func

        if isinstance(func, ast.Name):
            return func.id

        if isinstance(func, ast.Attribute):
            parts = [func.attr]
            value = func.value

            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value

            if isinstance(value, ast.Name):
                parts.append(value.id)

            return ".".join(reversed(parts))

        return ""

    def check_text_patterns(self) -> None:
        patterns = [
            ("HIGH", "TODO_LEFT", r"\bTODO\b", "发现 TODO。", "把 TODO 转为 issue 或明确处理计划。"),
            ("HIGH", "FIXME_LEFT", r"\bFIXME\b", "发现 FIXME。", "优先修复 FIXME。"),
            ("MEDIUM", "HARD_CODED_SECRET", r"(api_key|secret|token|password)\s*=\s*['\"][^'\"]+['\"]", "疑似硬编码密钥。", "改用环境变量或配置文件。"),
            ("MEDIUM", "LONG_LINE", r".{121,}", "存在超过 120 字符的长行。", "拆分长行，提高可读性。"),
        ]

        for index, line in enumerate(self.lines, start=1):
            for level, code, pattern, msg, suggestion in patterns:
                if re.search(pattern, line, flags=re.IGNORECASE):
                    self.add(level, code, index, msg, suggestion)

    def check_duplicate_lines(self) -> None:
        counter: dict[str, list[int]] = {}

        for index, line in enumerate(self.lines, start=1):
            text = line.strip()

            if not text:
                continue
            if text.startswith("#"):
                continue
            if len(text) < 20:
                continue

            counter.setdefault(text, []).append(index)

        for text, lines in counter.items():
            if len(lines) >= 4:
                self.add(
                    "LOW",
                    "DUPLICATE_LINE",
                    lines[0],
                    f"发现重复代码行，出现 {len(lines)} 次。",
                    "考虑提取为函数、常量或公共逻辑。",
                )

    def build_report(self) -> QualityReport:
        critical = sum(1 for x in self.issues if x.level == "CRITICAL")
        high = sum(1 for x in self.issues if x.level == "HIGH")
        medium = sum(1 for x in self.issues if x.level == "MEDIUM")
        low = sum(1 for x in self.issues if x.level == "LOW")

        score = 100
        score -= critical * 30
        score -= high * 15
        score -= medium * 7
        score -= low * 2
        score = max(0, score)

        return QualityReport(
            file=self.filename,
            score=score,
            total_issues=len(self.issues),
            critical=critical,
            high=high,
            medium=medium,
            low=low,
            issues=self.issues,
        )


def format_markdown(report: QualityReport) -> str:
    lines = []

    lines.append("# 代码质量报告")
    lines.append("")
    lines.append(f"文件：`{report.file}`")
    lines.append(f"质量评分：**{report.score}/100**")
    lines.append("")
    lines.append("## 问题统计")
    lines.append("")
    lines.append(f"- CRITICAL：{report.critical}")
    lines.append(f"- HIGH：{report.high}")
    lines.append(f"- MEDIUM：{report.medium}")
    lines.append(f"- LOW：{report.low}")
    lines.append(f"- TOTAL：{report.total_issues}")
    lines.append("")

    if not report.issues:
        lines.append("## 结果")
        lines.append("")
        lines.append("没有发现明显质量问题。")
        return "\n".join(lines)

    lines.append("## 问题列表")
    lines.append("")

    for issue in report.issues:
        lines.append(f"### {issue.level} / {issue.code}")
        lines.append("")
        lines.append(f"- 行号：{issue.line}")
        lines.append(f"- 问题：{issue.message}")
        lines.append(f"- 建议：{issue.suggestion}")
        lines.append("")

    lines.append("## 结论")
    lines.append("")

    if report.critical > 0:
        lines.append("不建议继续开发，先修复 CRITICAL 问题。")
    elif report.high > 0:
        lines.append("可以继续开发，但 HIGH 问题应优先修复。")
    elif report.medium > 0:
        lines.append("代码基本可用，建议逐步优化 MEDIUM 问题。")
    else:
        lines.append("代码质量较好，只存在轻微问题。")

    return "\n".join(lines)


def analyze_file(path: str | Path) -> QualityReport:
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(str(p))

    source = p.read_text(encoding="utf-8")
    guard = QualityGuard(source, str(p))
    return guard.check()


def main() -> None:
    parser = argparse.ArgumentParser(description="Python 代码质量检查器")
    parser.add_argument("file", help="要检查的 Python 文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--out", default="", help="保存报告到文件")

    args = parser.parse_args()

    report = analyze_file(args.file)

    if args.json:
        output = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    else:
        output = format_markdown(report)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
