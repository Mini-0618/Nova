"""
Codex-Local Eval Runner
Loads tasks.json, executes each task through CodexLoop, scores results.

Usage:
    python data/eval/run_eval.py                           # Run all tasks
    python data/eval/run_eval.py --category bugfix         # Run one category
    python data/eval/run_eval.py --task E11                # Run one task
    python data/eval/run_eval.py --report report.json      # Save report
    python data/eval/run_eval.py --dry-run                 # Show tasks without running
"""

import os
import sys
import json
import time
import asyncio
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EVAL_DIR = Path(__file__).resolve().parent
TASKS_FILE = EVAL_DIR / "tasks.json"
WORKSPACE = EVAL_DIR / "workspace"
REPORTS_DIR = EVAL_DIR / "reports"


@dataclass
class TaskResult:
    task_id: str
    category: str
    difficulty: str
    title: str
    passed: bool = False
    score: int = 0  # 0 or 1
    error: Optional[str] = None
    duration_s: float = 0.0
    tools_used: List[str] = field(default_factory=list)
    tool_calls_total: int = 0
    tool_calls_success: int = 0
    needed_human: bool = False
    introduced_regression: bool = False
    changed_wrong_files: bool = False
    patch_too_large: bool = False
    details: str = ""


@dataclass
class EvalReport:
    timestamp: str = ""
    total_tasks: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    by_category: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_difficulty: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tool_call_accuracy: float = 0.0
    regression_rate: float = 0.0
    false_change_rate: float = 0.0
    human_intervention_rate: float = 0.0
    results: List[Dict[str, Any]] = field(default_factory=list)


def load_tasks() -> List[Dict[str, Any]]:
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def setup_workspace(task: Dict[str, Any]):
    """Create setup files for a task."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    setup_files = task.get("setup_files", {})
    for rel_path, content in setup_files.items():
        full_path = PROJECT_ROOT / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)


def cleanup_workspace(task: Dict[str, Any]):
    """Remove setup files after task (optional, for clean state)."""
    # Don't cleanup - keep files for debugging
    pass


def verify_file_check(task: Dict[str, Any]) -> tuple[bool, str]:
    """Check file-based verification criteria."""
    verify_file = task.get("verify_file")
    if not verify_file:
        return True, "no file check required"

    full_path = PROJECT_ROOT / verify_file
    if not full_path.exists():
        return False, f"file not found: {verify_file}"

    content = full_path.read_text(encoding='utf-8')

    if "verify_contains" in task:
        if task["verify_contains"] not in content:
            return False, f"expected '{task['verify_contains']}' in {verify_file}, got: {content[:200]}"

    if "verify_not_contains" in task:
        if task["verify_not_contains"] in content:
            return False, f"unexpected '{task['verify_not_contains']}' found in {verify_file}"

    if "verify_min_length" in task:
        if len(content) < task["verify_min_length"]:
            return False, f"content too short: {len(content)} < {task['verify_min_length']}"

    if "verify_min_lines" in task:
        lines = content.strip().split('\n')
        if len(lines) < task["verify_min_lines"]:
            return False, f"too few lines: {len(lines)} < {task['verify_min_lines']}"

    return True, "file check passed"


def verify_test_check(task: Dict[str, Any]) -> tuple[bool, str]:
    """Run the verification test command."""
    verify_test = task.get("verify_test")
    if not verify_test:
        return True, "no test check required"

    # Replace 'python' with sys.executable for Windows compatibility
    import sys as _sys
    py = _sys.executable
    verify_test = verify_test.replace("python -m pytest", f'"{py}" -m pytest')
    verify_test = verify_test.replace("python -c", f'"{py}" -c')
    verify_test = verify_test.replace("python data/", f'"{py}" data/')
    # Handle 'python' at start of command
    if verify_test.startswith("python "):
        verify_test = f'"{py}" {verify_test[7:]}'

    try:
        result = subprocess.run(
            verify_test,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT)
        )

        output = result.stdout + result.stderr

        if result.returncode != 0:
            return False, f"test failed (exit {result.returncode}): {output[:500]}"

        if "verify_output_contains" in task:
            if task["verify_output_contains"] not in output:
                return False, f"expected '{task['verify_output_contains']}' in output, got: {output[:200]}"

        return True, f"test passed: {output[:200]}"

    except subprocess.TimeoutExpired:
        return False, "test timed out (30s)"
    except Exception as e:
        return False, f"test error: {e}"


def verify_task(task: Dict[str, Any]) -> tuple[bool, str]:
    """Run all verification checks for a task."""
    # File checks
    ok, msg = verify_file_check(task)
    if not ok:
        return False, msg

    # Test checks
    ok, msg = verify_test_check(task)
    if not ok:
        return False, msg

    return True, "all checks passed"


async def run_task_with_loop(task: Dict[str, Any], model: str = "deepseek-chat") -> TaskResult:
    """Execute a task using CodexLoop and verify the result."""
    result = TaskResult(
        task_id=task["id"],
        category=task["category"],
        difficulty=task["difficulty"],
        title=task["title"]
    )

    start_time = time.time()

    try:
        # Setup
        setup_workspace(task)

        # Run through CodexLoop
        from runtime.loop import CodexLoop, LoopConfig

        config = LoopConfig(
            model=model,
            max_iterations=15,
        )

        loop = CodexLoop(config)
        task_prompt = task["task"]

        # Load relevant lessons
        lessons_text = ""
        lessons_file = EVAL_DIR / "lessons.json"
        if lessons_file.exists():
            with open(lessons_file, 'r', encoding='utf-8') as f:
                lessons = json.load(f)
            relevant = []
            cat = task.get("category", "")
            for l in lessons:
                if l.get("category") == cat or any(w in task_prompt.lower() for w in l.get("pattern", "").lower().split()[:3]):
                    relevant.append(l)
            if relevant:
                lessons_text = "\nLessons from past failures:\n"
                for l in relevant[:3]:
                    lessons_text += f"- {l['pattern'][:80]} -> Fix: {l['fix'][:80]}\n"

        # Add verification instructions to the prompt
        full_prompt = f"""Task: {task_prompt}
{lessons_text}
After completing the task, verify your work:
- If the task asks you to run a test, run it.
- If the task creates a file, confirm it exists and has the right content.
- Report what you did and whether it worked."""

        loop_result = await loop.run_task(full_prompt)

        # Verify
        passed, details = verify_task(task)
        result.passed = passed
        result.score = 1 if passed else 0
        result.details = details

    except Exception as e:
        result.passed = False
        result.score = 0
        result.error = f"{type(e).__name__}: {str(e)}"
        result.details = f"Exception: {e}"

    finally:
        result.duration_s = round(time.time() - start_time, 2)

    return result


def run_task_offline(task: Dict[str, Any]) -> TaskResult:
    """Verify task setup files exist (offline/dry-run mode)."""
    result = TaskResult(
        task_id=task["id"],
        category=task["category"],
        difficulty=task["difficulty"],
        title=task["title"]
    )

    # Just check if setup and verification are defined
    has_setup = bool(task.get("setup_files"))
    has_verify = bool(task.get("verify_file") or task.get("verify_test"))
    result.details = f"setup={'yes' if has_setup else 'no'}, verify={'yes' if has_verify else 'no'}"
    result.passed = True  # dry run always "passes"
    result.score = 0  # but score is 0 (not actually tested)

    return result


def run_task_subprocess(task: Dict[str, Any]) -> TaskResult:
    """Verify task structure only (without LLM or code execution).

    This checks that the task is well-formed:
    - Has required fields
    - Setup files are valid
    - Verification criteria are defined
    Does NOT actually run the buggy code or tests.
    """
    result = TaskResult(
        task_id=task["id"],
        category=task["category"],
        difficulty=task["difficulty"],
        title=task["title"]
    )

    start_time = time.time()
    issues = []

    try:
        # Check required fields
        for field in ["id", "category", "difficulty", "title", "task"]:
            if not task.get(field):
                issues.append(f"missing field: {field}")

        # Check verification is defined
        has_verify = bool(task.get("verify_file") or task.get("verify_test"))
        if not has_verify:
            issues.append("no verification method defined")

        # Check expected_tools
        if not task.get("expected_tools"):
            issues.append("no expected_tools defined")

        # Setup files: check they're valid
        setup_files = task.get("setup_files", {})
        for path, content in setup_files.items():
            if not isinstance(content, str):
                issues.append(f"setup file {path}: content is not a string")

        # Score: well-formed = 1, has issues = 0
        result.passed = len(issues) == 0
        result.score = 1 if result.passed else 0
        result.details = "; ".join(issues) if issues else "task structure OK"

    except Exception as e:
        result.passed = False
        result.score = 0
        result.error = str(e)
        result.details = f"Exception: {e}"
    finally:
        result.duration_s = round(time.time() - start_time, 2)

    return result


def build_report(results: List[TaskResult]) -> EvalReport:
    """Build aggregate report from task results."""
    report = EvalReport(
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        total_tasks=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
    )

    if report.total_tasks > 0:
        report.pass_rate = round(report.passed / report.total_tasks * 100, 1)

    # By category
    cats = {}
    for r in results:
        if r.category not in cats:
            cats[r.category] = {"total": 0, "passed": 0, "failed": 0}
        cats[r.category]["total"] += 1
        if r.passed:
            cats[r.category]["passed"] += 1
        else:
            cats[r.category]["failed"] += 1
    for cat in cats:
        cats[cat]["pass_rate"] = round(cats[cat]["passed"] / cats[cat]["total"] * 100, 1) if cats[cat]["total"] > 0 else 0
    report.by_category = cats

    # By difficulty
    diffs = {}
    for r in results:
        if r.difficulty not in diffs:
            diffs[r.difficulty] = {"total": 0, "passed": 0, "failed": 0}
        diffs[r.difficulty]["total"] += 1
        if r.passed:
            diffs[r.difficulty]["passed"] += 1
        else:
            diffs[r.difficulty]["failed"] += 1
    for d in diffs:
        diffs[d]["pass_rate"] = round(diffs[d]["passed"] / diffs[d]["total"] * 100, 1) if diffs[d]["total"] > 0 else 0
    report.by_difficulty = diffs

    # Tool metrics
    total_calls = sum(r.tool_calls_total for r in results)
    success_calls = sum(r.tool_calls_success for r in results)
    report.tool_call_accuracy = round(success_calls / total_calls * 100, 1) if total_calls > 0 else 0

    report.regression_rate = round(sum(1 for r in results if r.introduced_regression) / report.total_tasks * 100, 1) if report.total_tasks > 0 else 0
    report.false_change_rate = round(sum(1 for r in results if r.changed_wrong_files) / report.total_tasks * 100, 1) if report.total_tasks > 0 else 0
    report.human_intervention_rate = round(sum(1 for r in results if r.needed_human) / report.total_tasks * 100, 1) if report.total_tasks > 0 else 0

    report.results = [asdict(r) for r in results]

    return report


def print_report(report: EvalReport):
    """Print human-readable report."""
    print("\n" + "=" * 60)
    print(f"  CODEX-LOCAL EVAL REPORT  |  {report.timestamp}")
    print("=" * 60)

    print(f"\n  Overall: {report.passed}/{report.total_tasks} passed ({report.pass_rate}%)")
    print(f"  Tool Call Accuracy: {report.tool_call_accuracy}%")
    print(f"  Regression Rate: {report.regression_rate}%")
    print(f"  False Change Rate: {report.false_change_rate}%")
    print(f"  Human Intervention: {report.human_intervention_rate}%")

    print("\n  By Category:")
    for cat, stats in sorted(report.by_category.items()):
        bar = "#" * int(stats["pass_rate"] / 5) + "." * (20 - int(stats["pass_rate"] / 5))
        print(f"    {cat:15s} {bar} {stats['passed']}/{stats['total']} ({stats['pass_rate']}%)")

    print("\n  By Difficulty:")
    for diff, stats in sorted(report.by_difficulty.items()):
        bar = "#" * int(stats["pass_rate"] / 5) + "." * (20 - int(stats["pass_rate"] / 5))
        print(f"    {diff:15s} {bar} {stats['passed']}/{stats['total']} ({stats['pass_rate']}%)")

    # Show failures
    failures = [r for r in report.results if not r["passed"]]
    if failures:
        print(f"\n  Failures ({len(failures)}):")
        for r in failures:
            print(f"    [{r['task_id']}] {r['title']}")
            if r.get("error"):
                print(f"      Error: {r['error'][:100]}")
            if r.get("details"):
                print(f"      Details: {r['details'][:100]}")

    print("\n" + "=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Codex-Local Eval Runner")
    parser.add_argument("--category", help="Run only tasks in this category")
    parser.add_argument("--task", help="Run only this task ID (e.g. E11)")
    parser.add_argument("--difficulty", help="Run only this difficulty level")
    parser.add_argument("--model", default="deepseek-chat", help="Model to use")
    parser.add_argument("--report", default=None, help="Save JSON report to this path")
    parser.add_argument("--dry-run", action="store_true", help="Show tasks without executing")
    parser.add_argument("--offline", action="store_true", help="Run verification only (no LLM)")
    parser.add_argument("--setup-only", action="store_true", help="Only setup fixtures, don't run")
    args = parser.parse_args()

    tasks = load_tasks()

    # Filter
    if args.category:
        tasks = [t for t in tasks if t["category"] == args.category]
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]
    if args.difficulty:
        tasks = [t for t in tasks if t["difficulty"] == args.difficulty]

    if not tasks:
        print("No tasks matched filters.")
        return

    print(f"\nRunning {len(tasks)} eval tasks...")
    print(f"Mode: {'dry-run' if args.dry_run else 'offline' if args.offline else 'full (LLM)'}\n")

    if args.setup_only:
        for task in tasks:
            setup_workspace(task)
            print(f"  [{task['id']}] {task['title']} — setup done")
        return

    results = []
    for i, task in enumerate(tasks, 1):
        print(f"  [{i}/{len(tasks)}] {task['id']}: {task['title']}...", end=" ", flush=True)

        if args.dry_run:
            result = run_task_offline(task)
        elif args.offline:
            result = run_task_subprocess(task)
        else:
            result = await run_task_with_loop(task, model=args.model)

        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"{status} ({result.duration_s}s)")

        if not result.passed and result.details:
            print(f"           {result.details[:80]}")

        results.append(result)

    # Build and print report
    report = build_report(results)
    print_report(report)

    # Save report
    if args.report:
        report_path = Path(args.report)
    else:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
