"""
Codex-Local 准确率提升脚本

当前: 74% (37/50)
目标: 92% (46/50)

策略:
1. 注入 21 条经验到 prompt
2. 用 MCR 沙箱验证生成的代码
3. 自动修复常见错误模式
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CODEX_ROOT = Path(__file__).parent
sys.path.insert(0, str(CODEX_ROOT))


def load_lessons() -> list[dict]:
    """加载 21 条经验。"""
    lessons_file = CODEX_ROOT / "data" / "eval" / "lessons.json"
    if lessons_file.exists():
        return json.loads(lessons_file.read_text(encoding="utf-8"))
    return []


def load_failed_tasks() -> list[dict]:
    """加载失败的 13 个任务。"""
    report_file = CODEX_ROOT / "data" / "eval" / "reports" / "eval-llm-v2.json"
    if not report_file.exists():
        return []

    d = json.loads(report_file.read_text(encoding="utf-8"))
    results = d.get("results", d.get("tasks", []))
    return [r for r in results if not r.get("passed")]


def build_enhanced_prompt(task: dict, lessons: list[dict]) -> str:
    """构建增强 prompt，注入经验。"""
    task_id = task.get("task_id", "?")
    title = task.get("title", "")
    category = task.get("category", "")

    # 找相关经验
    relevant_lessons = []
    for l in lessons:
        pattern = l.get("pattern", "").lower()
        cat = l.get("category", "").lower()
        # 匹配任务类别
        if cat in category.lower() or category.lower() in cat:
            relevant_lessons.append(l)
        # 匹配常见错误模式
        elif any(kw in pattern for kw in ["tool call", "import", "attribute", "syntax", "file"]):
            relevant_lessons.append(l)

    # 去重
    seen = set()
    unique_lessons = []
    for l in relevant_lessons:
        lid = l.get("id", "")
        if lid not in seen:
            seen.add(lid)
            unique_lessons.append(l)

    lessons_text = ""
    if unique_lessons:
        lessons_text = "\n\n## Past Lessons (learned from failures):\n"
        for l in unique_lessons[:10]:
            lessons_text += f"- **{l.get('pattern', '')}** → Fix: {l.get('fix', '')}\n"

    prompt = f"""You are a coding assistant. Complete the following task by using tools to create/modify files and run commands.

Task: {title}
Category: {category}
Task ID: {task_id}

IMPORTANT RULES:
1. USE TOOLS to create/modify files - do NOT just describe the code in text
2. Write the code to a file using the write_file tool
3. Run tests using the run_command tool
4. If tests fail, fix the code and try again
5. Keep trying until tests pass or you've made 5 attempts
{lessons_text}

Start by creating the implementation file, then run tests.
"""

    return prompt


def analyze_failure_pattern(task: dict) -> dict:
    """分析失败模式，给出修复建议。"""
    tools_used = task.get("tool_calls_total", 0)
    error = task.get("error") or ""
    details = task.get("details") or ""
    category = task.get("category", "")

    if tools_used == 0:
        return {
            "pattern": "no_tool_calls",
            "fix": "Model must use tools (write_file, run_command) instead of describing code in text",
            "priority": "CRITICAL",
        }

    if "timeout" in error.lower():
        return {
            "pattern": "timeout",
            "fix": "Reduce task complexity or increase timeout",
            "priority": "HIGH",
        }

    if "syntaxerror" in error.lower():
        return {
            "pattern": "syntax_error",
            "fix": "Validate Python syntax before submitting",
            "priority": "MEDIUM",
        }

    if "assertionerror" in error.lower() or "assert" in error.lower():
        return {
            "pattern": "wrong_implementation",
            "fix": "Read test requirements more carefully, check edge cases",
            "priority": "MEDIUM",
        }

    if "importerror" in error.lower() or "modulenotfounderror" in error.lower():
        return {
            "pattern": "missing_import",
            "fix": "Check available modules, use only standard library",
            "priority": "MEDIUM",
        }

    return {
        "pattern": "unknown",
        "fix": "Manual review needed",
        "priority": "LOW",
    }


def generate_fix_plan(failed_tasks: list[dict], lessons: list[dict]) -> str:
    """生成修复计划。"""
    plan = "# Codex-Local 准确率提升计划\n\n"
    plan += f"当前: 74% (37/50)\n"
    plan += f"目标: 92% (46/50)\n"
    plan += f"需要修复: {46-37} 个任务\n\n"

    # 按失败模式分类
    patterns = {}
    for t in failed_tasks:
        analysis = analyze_failure_pattern(t)
        pattern = analysis["pattern"]
        if pattern not in patterns:
            patterns[pattern] = []
        patterns[pattern].append((t, analysis))

    plan += "## 失败模式分析\n\n"
    for pattern, tasks in sorted(patterns.items(), key=lambda x: -len(x[1])):
        plan += f"### {pattern} ({len(tasks)} 个任务)\n\n"
        for t, a in tasks:
            plan += f"- **{t.get('task_id')}**: {t.get('title', '')[:50]}\n"
            plan += f"  - 修复: {a['fix']}\n"
            plan += f"  - 优先级: {a['priority']}\n"
        plan += "\n"

    plan += "## 修复策略\n\n"
    plan += "1. **注入经验**: 把 21 条 lessons 注入 system prompt\n"
    plan += "2. **强制工具调用**: 在 prompt 中明确要求使用 write_file 和 run_command\n"
    plan += "3. **沙箱验证**: 用 MCR 沙箱验证生成的代码\n"
    plan += "4. **自动重试**: 失败后自动修复并重试\n"
    plan += "5. **经验反馈**: 每次成功/失败都更新 lessons\n"

    return plan


def main():
    lessons = load_lessons()
    failed = load_failed_tasks()

    print(f"Lessons loaded: {len(lessons)}")
    print(f"Failed tasks: {len(failed)}")
    print()

    # 分析失败模式
    for t in failed:
        analysis = analyze_failure_pattern(t)
        print(f"  {t.get('task_id'):4s} [{analysis['priority']:8s}] {analysis['pattern']:20s} → {analysis['fix'][:60]}")

    print()

    # 生成修复计划
    plan = generate_fix_plan(failed, lessons)
    plan_file = CODEX_ROOT / "data" / "eval" / "boost_plan.md"
    plan_file.write_text(plan, encoding="utf-8")
    print(f"Fix plan saved: {plan_file}")

    # 生成增强 prompt 示例
    if failed:
        example_task = failed[0]
        enhanced_prompt = build_enhanced_prompt(example_task, lessons)
        print(f"\n=== Enhanced Prompt Example ({example_task.get('task_id')}) ===")
        print(enhanced_prompt[:500])


if __name__ == "__main__":
    main()
