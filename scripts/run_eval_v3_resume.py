"""
Nova's Honest Eval v3 - Resumable
Run all 50 tasks with incremental progress saving.
"""

import asyncio
import json
import os
import sys
import time
import importlib.util
from pathlib import Path
from dataclasses import asdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ['DEEPSEEK_API_KEY'] = 'sk-842a3aa4bbcb482a89482585aa227171'

# Direct import using spec (avoids package path issues)
_eval_path = str(ROOT / "data" / "eval" / "run_eval.py").replace("\\", "/")
_spec = importlib.util.spec_from_file_location("run_eval", _eval_path)
_run_eval = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_run_eval)

load_tasks = _run_eval.load_tasks
run_task_with_loop = _run_eval.run_task_with_loop
build_report = _run_eval.build_report
TaskResult = _run_eval.TaskResult

PROGRESS_FILE = ROOT / "data" / "eval" / "reports" / "eval-honest-v3-progress.json"
REPORT_FILE = ROOT / "data" / "eval" / "reports" / "eval-honest-v3.json"


def load_progress():
    """Load already-completed task results."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"results": [], "completed_ids": []}


def save_progress(progress):
    """Save progress incrementally."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def result_to_dict(r):
    """Convert TaskResult to dict."""
    return {
        "task_id": r.task_id,
        "category": r.category,
        "difficulty": r.difficulty,
        "title": r.title,
        "passed": r.passed,
        "score": r.score,
        "error": r.error,
        "duration_s": r.duration_s,
        "tools_used": r.tools_used,
        "tool_calls_total": r.tool_calls_total,
        "tool_calls_success": r.tool_calls_success,
        "details": r.details,
        "quality_score": r.quality_score,
        "quality_issues": r.quality_issues,
    }


async def main():
    print("=" * 60, flush=True)
    print("  NOVA HONEST EVAL v3 (Resumable)", flush=True)
    print("=" * 60, flush=True)

    tasks = load_tasks()
    progress = load_progress()
    completed_ids = set(progress.get("completed_ids", []))
    existing_results = progress.get("results", [])

    print(f"\nLoaded {len(tasks)} tasks, {len(completed_ids)} already completed", flush=True)

    results = []
    start = time.time()

    for i, task in enumerate(tasks, 1):
        task_id = task["id"]

        # Skip already completed
        if task_id in completed_ids:
            print(f"[{i}/{len(tasks)}] {task_id}: {task['title']} -> SKIPPED (already done)", flush=True)
            # Find existing result
            for er in existing_results:
                if er["task_id"] == task_id:
                    results.append(er)
                    break
            continue

        t0 = time.time()
        print(f"[{i}/{len(tasks)}] {task_id}: {task['title']} ({task['difficulty']})", end=" ", flush=True)

        try:
            r = await run_task_with_loop(task, model="deepseek-chat")
            status = "PASS" if r.passed else "FAIL"
            print(f"-> {status} ({r.duration_s}s)", flush=True)
            if not r.passed:
                print(f"   Error: {r.details[:120]}", flush=True)
            rdict = result_to_dict(r)
        except Exception as e:
            print(f"-> EXCEPTION: {e}", flush=True)
            rdict = {
                "task_id": task_id,
                "category": task["category"],
                "difficulty": task["difficulty"],
                "title": task["title"],
                "passed": False,
                "error": str(e),
                "details": f"Exception: {e}",
                "duration_s": round(time.time() - t0, 2),
                "tools_used": [],
                "tool_calls_total": 0,
                "tool_calls_success": 0,
                "quality_score": 0.0,
                "quality_issues": 0,
                "score": 0,
            }

        results.append(rdict)
        completed_ids.add(task_id)

        # Save progress after each task
        progress["results"] = results
        progress["completed_ids"] = list(completed_ids)
        save_progress(progress)

    total_time = time.time() - start

    # Build final report
    passed = sum(1 for r in results if (r.get("passed") if isinstance(r, dict) else r.passed))
    total = len(results)
    rate = round(passed / total * 100, 1) if total > 0 else 0

    # Group by category
    by_cat = {}
    for r in results:
        cat = r.get("category", "unknown") if isinstance(r, dict) else r.category
        if cat not in by_cat:
            by_cat[cat] = {"total": 0, "passed": 0, "failed": 0}
        by_cat[cat]["total"] += 1
        p = r.get("passed", False) if isinstance(r, dict) else r.passed
        if p:
            by_cat[cat]["passed"] += 1
        else:
            by_cat[cat]["failed"] += 1
    for cat in by_cat:
        t = by_cat[cat]["total"]
        p = by_cat[cat]["passed"]
        by_cat[cat]["pass_rate"] = round(p / t * 100, 1) if t > 0 else 0

    # Group by difficulty
    by_diff = {}
    for r in results:
        diff = r.get("difficulty", "unknown") if isinstance(r, dict) else r.difficulty
        if diff not in by_diff:
            by_diff[diff] = {"total": 0, "passed": 0, "failed": 0}
        by_diff[diff]["total"] += 1
        p = r.get("passed", False) if isinstance(r, dict) else r.passed
        if p:
            by_diff[diff]["passed"] += 1
        else:
            by_diff[diff]["failed"] += 1
    for d in by_diff:
        t = by_diff[d]["total"]
        p = by_diff[d]["passed"]
        by_diff[d]["pass_rate"] = round(p / t * 100, 1) if t > 0 else 0

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "eval_version": "honest-v3",
        "model": "deepseek-chat",
        "total_tasks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": rate,
        "total_time_s": round(total_time, 1),
        "avg_time_per_task": round(total_time / total, 1) if total > 0 else 0,
        "by_category": by_cat,
        "by_difficulty": by_diff,
        "results": results,
        "note": "Full honest eval by Nova during autonomous session",
    }

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}", flush=True)
    print(f"  FINAL RESULTS", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Accuracy: {passed}/{total} ({rate}%)", flush=True)
    print(f"  Time: {total_time/60:.1f} minutes", flush=True)
    print(f"\n  By Category:", flush=True)
    for cat, stats in sorted(by_cat.items()):
        print(f"    {cat}: {stats['passed']}/{stats['total']} ({stats['pass_rate']}%)", flush=True)
    print(f"\n  By Difficulty:", flush=True)
    for diff, stats in sorted(by_diff.items()):
        print(f"    {diff}: {stats['passed']}/{stats['total']} ({stats['pass_rate']}%)", flush=True)

    failures = [r for r in results if not (r.get("passed") if isinstance(r, dict) else r.passed)]
    if failures:
        print(f"\n  Failures ({len(failures)}):", flush=True)
        for r in failures:
            tid = r.get("task_id", "?")
            title = r.get("title", "?")
            det = r.get("details", "")[:80]
            print(f"    [{tid}] {title}: {det}", flush=True)

    print(f"\n  Report saved to: {REPORT_FILE}", flush=True)

    return report


if __name__ == "__main__":
    asyncio.run(main())
