"""
Nova Phase 3: Targeted fix for the 12 failing tasks.
Run only the failing tasks, analyze failures, attempt fixes.
"""

import os, sys, asyncio, json, time
from pathlib import Path

os.environ['DEEPSEEK_API_KEY'] = 'sk-842a3aa4bbcb482a89482585aa227171'
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataclasses import asdict
from data.eval.run_eval import load_tasks, run_task_with_loop, build_report

# The 12 failing task IDs from Phase 1
# E46 is excluded - it's a self-destructive task that overwrites run_eval.py
FAILING_TASKS = ['E08', 'E09', 'E23', 'E33', 'E40', 'E41', 'E42', 'E44', 'E45', 'E47', 'E50']

async def run_failing_tasks(tasks, model='deepseek-chat'):
    """Run only the failing tasks."""
    results = []
    for i, task in enumerate(tasks):
        print(f'[{i+1}/{len(tasks)}] {task["id"]}: {task["title"][:40]}...', end=" ", flush=True)
        r = await run_task_with_loop(task, model=model)
        mark = 'PASS' if r.passed else 'FAIL'
        print(f'{mark} ({r.duration_s}s)')
        if not r.passed:
            print(f'  -> {r.details[:120]}')
        results.append(r)
    return results

async def main():
    all_tasks = load_tasks()
    failing_tasks = [t for t in all_tasks if t['id'] in FAILING_TASKS]
    print(f"Running {len(failing_tasks)} previously failing tasks (excluding E46 self-destructive)...")
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = await run_failing_tasks(failing_tasks)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print(f"\n{'='*50}")
    print(f"  Phase 3 Round 1 Results")
    print(f"{'='*50}")
    print(f"  Fixed: {passed}/{len(results)}")
    print(f"  Still failing: {failed}/{len(results)}")

    still_failing = [r for r in results if not r.passed]
    if still_failing:
        print(f"\n  Still failing:")
        for r in still_failing:
            print(f"    [{r.task_id}] {r.title}: {r.details[:80]}")

    # Save results
    report_path = ROOT / 'data' / 'eval' / 'reports' / 'phase3-round1.json'
    report = build_report(results)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved to: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
