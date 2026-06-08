"""
Progressive Difficulty Eval Runner
Instead of running all 50 tasks at once, runs in phases:
1. Easy tasks first (build confidence)
2. Medium tasks (accumulate experience)
3. Hard tasks (test limits)

Each phase learns from the previous one.

Nova's Innovation #5
"""

import asyncio
import json
import os
import sys
import time
import importlib.util
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ['DEEPSEEK_API_KEY'] = 'sk-842a3aa4bbcb482a89482585aa227171'

# Import eval modules
_eval_path = str(ROOT / "data" / "eval" / "run_eval.py").replace("\\", "/")
_spec = importlib.util.spec_from_file_location("run_eval", _eval_path)
_run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_run_eval)

from runtime.cross_task_learner import get_learner
from runtime.reflection import get_reflection_writer


PHASES = [
    {"name": "Phase 1: Foundation", "difficulty": "easy", "description": "Build confidence with simple tasks"},
    {"name": "Phase 2: Building Skills", "difficulty": "medium", "description": "Accumulate experience"},
    {"name": "Phase 3: Stress Test", "difficulty": "hard", "description": "Test limits with hard tasks"},
]


async def run_phase(phase: Dict, tasks: List[Dict], model: str = "deepseek-chat") -> Dict:
    """Run one phase of progressive difficulty."""
    print(f"\n{'='*60}")
    print(f"  {phase['name']}")
    print(f"  {phase['description']}")
    print(f"  Tasks: {len(tasks)}")
    print(f"{'='*60}")

    learner = get_learner()
    reflection_writer = get_reflection_writer()

    results = []
    phase_start = time.time()

    for i, task in enumerate(tasks, 1):
        task_id = task["id"]
        print(f"\n  [{i}/{len(tasks)}] {task_id}: {task['title']}", end=" ", flush=True)

        # Inject cross-task learning from previous phases
        learning_context = learner.get_learning_injection(
            task["task"], task.get("category", "")
        )

        t0 = time.time()
        try:
            r = await _run_eval.run_task_with_loop(task, model=model)
            status = "PASS" if r.passed else "FAIL"
            print(f"-> {status} ({r.duration_s}s)", flush=True)

            if not r.passed:
                print(f"   {r.details[:100]}", flush=True)

            # Write reflection
            reflection_writer.write_reflection(
                task_id=task_id,
                task_description=task["task"],
                tools_used=r.tools_used,
                iterations=r.tool_calls_total,
                passed=r.passed,
                error=r.details if not r.passed else "",
                duration_s=r.duration_s,
                details=r.details,
            )

            # Record learning
            if not r.passed:
                learner.record_learning(
                    task_id=task_id,
                    category=task.get("category", ""),
                    pattern=f"{task['title']} failed: {r.details[:80]}",
                    fix=f"Need to fix: {r.details[:100]}",
                )

            results.append({
                "task_id": task_id,
                "passed": r.passed,
                "duration_s": r.duration_s,
                "details": r.details,
                "error": r.error,
            })

        except Exception as e:
            print(f"-> EXCEPTION: {e}", flush=True)
            results.append({
                "task_id": task_id,
                "passed": False,
                "duration_s": round(time.time() - t0, 2),
                "error": str(e),
                "details": f"Exception: {e}",
            })

    phase_time = time.time() - phase_start
    passed = sum(1 for r in results if r["passed"])

    return {
        "phase": phase["name"],
        "difficulty": phase["difficulty"],
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results) * 100, 1) if results else 0,
        "time_s": round(phase_time, 1),
        "results": results,
    }


async def main():
    print("=" * 60)
    print("  NOVA PROGRESSIVE DIFFICULTY EVAL")
    print("  Easy -> Medium -> Hard, learning between phases")
    print("=" * 60)

    tasks = _run_eval.load_tasks()
    model = "deepseek-chat"

    # Group tasks by difficulty
    by_difficulty = {"easy": [], "medium": [], "hard": []}
    for t in tasks:
        diff = t.get("difficulty", "medium")
        if diff in by_difficulty:
            by_difficulty[diff].append(t)

    print(f"\nTask distribution:")
    for diff, tsks in by_difficulty.items():
        print(f"  {diff}: {len(tsks)} tasks")

    # Run phases
    all_results = []
    overall_start = time.time()

    for phase in PHASES:
        diff = phase["difficulty"]
        phase_tasks = by_difficulty.get(diff, [])
        if not phase_tasks:
            print(f"\nNo {diff} tasks, skipping phase")
            continue

        phase_result = await run_phase(phase, phase_tasks, model)
        all_results.append(phase_result)

        print(f"\n  Phase Result: {phase_result['passed']}/{phase_result['total']} "
              f"({phase_result['pass_rate']}%) in {phase_result['time_s']/60:.1f}min")

    # Final report
    total_time = time.time() - overall_start
    total_passed = sum(r["passed"] for r in all_results)
    total_tasks = sum(r["total"] for r in all_results)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "eval_version": "progressive-v1",
        "model": model,
        "total_tasks": total_tasks,
        "passed": total_passed,
        "failed": total_tasks - total_passed,
        "pass_rate": round(total_passed / total_tasks * 100, 1) if total_tasks else 0,
        "total_time_s": round(total_time, 1),
        "phases": all_results,
    }

    # Save report
    report_path = ROOT / "data" / "eval" / "reports" / "eval-progressive-v1.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  PROGRESSIVE EVAL COMPLETE")
    print(f"{'='*60}")
    print(f"  Total: {total_passed}/{total_tasks} ({report['pass_rate']}%)")
    print(f"  Time: {total_time/60:.1f} minutes")
    for r in all_results:
        print(f"  {r['phase']}: {r['passed']}/{r['total']} ({r['pass_rate']}%)")
    print(f"\n  Report: {report_path}")

    return report


if __name__ == "__main__":
    asyncio.run(main())
