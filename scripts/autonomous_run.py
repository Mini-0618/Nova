"""
Autonomous Run Controller
One-shot: eval -> analyze -> fix -> data collect -> report -> git commit

Usage:
    python scripts/autonomous_run.py                   # 1 cycle
    python scripts/autonomous_run.py --cycles 3        # 3 cycles
    python scripts/autonomous_run.py --model mimo-v2.5 # use specific model
    python scripts/autonomous_run.py --dry-run         # show plan only
"""

import sys
import json
import time
import asyncio
import argparse
import subprocess
from pathlib import Path
from dataclasses import asdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def git_commit(message: str) -> bool:
    """Auto git add + commit. Returns True if successful."""
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=30,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            # Get short hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10,
            )
            short_hash = hash_result.stdout.strip()
            print(f"  Git commit: {short_hash} - {message}")
            return True
        else:
            if "nothing to commit" in result.stdout + result.stderr:
                print(f"  Git: nothing to commit")
            else:
                print(f"  Git commit failed: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"  Git error: {e}")
        return False


async def run_eval_cycle(model: str) -> dict:
    """Run one eval cycle and return the report dict."""
    from data.eval.run_eval import load_tasks, run_task_with_loop, build_report, REPORTS_DIR

    tasks = load_tasks()
    total = len(tasks)
    print(f"\n  Running {total} eval tasks with model={model}...")

    results = []
    for i, task in enumerate(tasks, 1):
        task_id = task["id"]
        title = task.get("title", "?")[:40]
        print(f"    [{i}/{total}] {task_id}: {title}...", end=" ", flush=True)

        result = await run_task_with_loop(task, model=model)
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} ({result.duration_s}s)")

        if not result.passed and result.details:
            print(f"             {result.details[:70]}")

        results.append(result)

    report = build_report(results)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"auto-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)

    return {
        "report": asdict(report),
        "report_path": str(report_path),
        "pass_rate": report.pass_rate,
        "passed": report.passed,
        "total": report.total_tasks,
        "quality_score": report.avg_quality_score,
    }


async def run_lesson_extraction(report_path: str, model: str) -> int:
    """Extract lessons from eval report. Returns number of new lessons."""
    from data.eval.auto_lessons import extract_lessons_from_report
    new_lessons = await extract_lessons_from_report(report_path, model=model)
    return len(new_lessons)


async def run_self_improvement(model: str) -> dict:
    """Run self-improvement cycle (retry failed tasks with fixes)."""
    from data.eval.self_improve_loop import (
        load_lessons, run_improvement_cycle, ProgressTracker
    )
    from data.eval.run_eval import load_tasks, run_task_with_loop, build_report

    tasks = load_tasks()
    lessons = load_lessons()

    # Run eval to find failures
    results = []
    for task in tasks:
        result = await run_task_with_loop(task, model=model)
        results.append(result)

    report = build_report(results)
    pass_rate = report.pass_rate

    # Collect failures
    failed_tasks = []
    failed_results = []
    for task, result in zip(tasks, results):
        if not result.passed:
            failed_tasks.append(task)
            failed_results.append(asdict(result))

    improvement = {
        "pass_rate_before": pass_rate,
        "tasks_fixed": 0,
        "lessons_generated": 0,
        "failed_count": len(failed_tasks),
    }

    if not failed_tasks:
        print("  All tasks passing, no improvement needed.")
        return improvement

    # Run improvement cycle
    cycle = await run_improvement_cycle(
        1, failed_tasks, failed_results, lessons,
        model=model, dry_run=False, use_llm_verify=False,
    )

    improvement["pass_rate_before"] = cycle.eval_pass_rate_before
    improvement["pass_rate_after"] = cycle.eval_pass_rate_after
    improvement["tasks_fixed"] = len(cycle.tasks_fixed)
    improvement["lessons_generated"] = len(cycle.lessons_generated)

    return improvement


async def run_cycle(cycle_num: int, model: str, dry_run: bool = False) -> dict:
    """Run one full autonomous cycle."""
    cycle_start = time.time()
    print(f"\n{'='*60}")
    print(f"  AUTONOMOUS CYCLE {cycle_num}")
    print(f"  Model: {model}")
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    result = {
        "cycle": cycle_num,
        "model": model,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    if dry_run:
        print("\n  [DRY RUN] Would execute:")
        print("    1. Run eval on all tasks")
        print("    2. Extract lessons from failures")
        print("    3. Run self-improvement (fix failed tasks)")
        print("    4. Re-evaluate")
        print("    5. Git commit")
        return result

    # Step 1: Run eval
    print("\n  Step 1/4: Running eval...")
    eval_result = await run_eval_cycle(model)
    result["eval"] = eval_result
    print(f"\n  Eval result: {eval_result['passed']}/{eval_result['total']} passed ({eval_result['pass_rate']}%)")
    if eval_result.get("quality_score"):
        print(f"  Quality score: {eval_result['quality_score']}/100")

    # Step 2: Extract lessons
    print("\n  Step 2/4: Extracting lessons from failures...")
    new_lessons = await run_lesson_extraction(eval_result["report_path"], model)
    result["new_lessons"] = new_lessons
    print(f"  New lessons: {new_lessons}")

    # Step 3: Self-improvement
    print("\n  Step 3/4: Running self-improvement...")
    improvement = await run_self_improvement(model)
    result["improvement"] = improvement
    print(f"  Tasks fixed: {improvement.get('tasks_fixed', 0)}")

    # Step 4: Git commit
    print("\n  Step 4/4: Git commit...")
    commit_msg = (
        f"auto-cycle-{cycle_num}: "
        f"pass_rate={eval_result['pass_rate']}%, "
        f"lessons={new_lessons}, "
        f"fixed={improvement.get('tasks_fixed', 0)}"
    )
    git_commit(commit_msg)

    result["duration_s"] = round(time.time() - cycle_start, 1)
    print(f"\n  Cycle {cycle_num} complete in {result['duration_s']}s")

    return result


def write_summary_report(cycle_results: list) -> str:
    """Write a summary report of all cycles."""
    lines = [
        "# Autonomous Run Summary",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Cycles: {len(cycle_results)}",
        "",
        "## Cycle Results",
        "",
        "| Cycle | Pass Rate | New Lessons | Tasks Fixed | Duration |",
        "|-------|-----------|-------------|-------------|----------|",
    ]

    for r in cycle_results:
        cycle = r.get("cycle", "?")
        pass_rate = r.get("eval", {}).get("pass_rate", "N/A")
        lessons = r.get("new_lessons", 0)
        fixed = r.get("improvement", {}).get("tasks_fixed", 0)
        duration = r.get("duration_s", 0)
        lines.append(f"| {cycle} | {pass_rate}% | {lessons} | {fixed} | {duration}s |")

    lines.append("")

    # Progress
    pass_rates = [r.get("eval", {}).get("pass_rate", 0) for r in cycle_results if r.get("eval")]
    if len(pass_rates) >= 2:
        trend = "improving" if pass_rates[-1] > pass_rates[0] else "stagnant"
        if pass_rates[-1] < pass_rates[0]:
            trend = "regressing"
        lines.append(f"## Trend: {trend}")
        lines.append("")
        lines.append(f"Pass rates: {' -> '.join(f'{r:.1f}%' for r in pass_rates)}")
        lines.append("")

    report = "\n".join(lines)

    report_dir = PROJECT_ROOT / "data" / "eval" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"autonomous-summary-{time.strftime('%Y%m%d-%H%M%S')}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nSummary saved to: {report_path}")

    return str(report_path)


async def main():
    parser = argparse.ArgumentParser(description="Codex-Local Autonomous Runner")
    parser.add_argument("--cycles", type=int, default=1, help="Number of cycles to run")
    parser.add_argument("--model", default="deepseek-chat", help="LLM model to use")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()

    print("=" * 60)
    print("  CODEX-LOCAL AUTONOMOUS RUNNER")
    print("=" * 60)
    print(f"  Cycles: {args.cycles}")
    print(f"  Model: {args.model}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = time.time()
    cycle_results = []

    for cycle in range(1, args.cycles + 1):
        try:
            result = await run_cycle(cycle, args.model, dry_run=args.dry_run)
            cycle_results.append(result)
        except Exception as e:
            print(f"\n  Cycle {cycle} failed with error: {e}")
            import traceback
            traceback.print_exc()
            cycle_results.append({
                "cycle": cycle,
                "error": str(e),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    # Write summary
    if cycle_results:
        write_summary_report(cycle_results)

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  AUTONOMOUS RUN COMPLETE")
    print(f"  Total time: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  Cycles completed: {len(cycle_results)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
