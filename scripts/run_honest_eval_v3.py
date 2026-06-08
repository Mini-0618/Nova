"""
Nova's Honest Eval v3
Run all 50 tasks, no skipping, no selection.
Save to data/eval/reports/eval-honest-v3.json
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from dataclasses import asdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ['DEEPSEEK_API_KEY'] = 'sk-842a3aa4bbcb482a89482585aa227171'

from data.eval.run_eval import load_tasks, run_task_with_loop, build_report, print_report


async def main():
    print("=" * 60)
    print("  NOVA HONEST EVAL v3")
    print("  All 50 tasks, no skipping")
    print("=" * 60)

    tasks = load_tasks()
    print(f"\nLoaded {len(tasks)} tasks")

    results = []
    start = time.time()

    for i, task in enumerate(tasks, 1):
        task_start = time.time()
        print(f"\n[{i}/{len(tasks)}] {task['id']}: {task['title']} ({task['difficulty']})")

        try:
            result = await run_task_with_loop(task, model="deepseek-chat")
            status = "PASS" if result.passed else "FAIL"
            print(f"  -> {status} ({result.duration_s}s)")
            if not result.passed:
                print(f"  -> Error: {result.details[:120]}")
            results.append(result)
        except Exception as e:
            print(f"  -> EXCEPTION: {e}")
            # Create a failed result
            from data.eval.run_eval import TaskResult
            result = TaskResult(
                task_id=task["id"],
                category=task["category"],
                difficulty=task["difficulty"],
                title=task["title"],
                passed=False,
                error=str(e),
                details=f"Exception: {e}",
                duration_s=round(time.time() - task_start, 2)
            )
            results.append(result)

        # Save intermediate results every 5 tasks
        if i % 5 == 0:
            elapsed = time.time() - start
            passed_so_far = sum(1 for r in results if r.passed)
            print(f"\n  --- Progress: {passed_so_far}/{i} passed ({elapsed/60:.1f}min elapsed) ---")

    total_time = time.time() - start

    # Build report
    report = build_report(results)
    print_report(report)

    # Save to specified location
    report_path = ROOT / "data" / "eval" / "reports" / "eval-honest-v3.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_dict = asdict(report)
    report_dict["total_time_s"] = round(total_time, 1)
    report_dict["avg_time_per_task"] = round(total_time / len(results), 1)
    report_dict["eval_version"] = "honest-v3"
    report_dict["model"] = "deepseek-chat"
    report_dict["note"] = "Full honest eval by Nova during autonomous session"

    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    print(f"\nReport saved to: {report_path}")
    print(f"Total time: {total_time/60:.1f} minutes")
    print(f"Accuracy: {report.pass_rate}%")

    return report_dict


if __name__ == "__main__":
    asyncio.run(main())
