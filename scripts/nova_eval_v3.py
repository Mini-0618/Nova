"""
Nova Phase 1: Honest Full 50-Task Eval
Run all tasks without skipping, save real results.
"""

import os, sys, asyncio, json, time
os.environ['DEEPSEEK_API_KEY'] = 'sk-842a3aa4bbcb482a89482585aa227171'
sys.path.insert(0, 'D:/codex-local')

from dataclasses import asdict
from data.eval.run_eval import load_tasks, run_task_with_loop, build_report

async def main():
    tasks = load_tasks()
    print(f"Starting honest eval of {len(tasks)} tasks...")
    print(f"Model: deepseek-chat")
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results = []
    for i, task in enumerate(tasks):
        task_start = time.time()
        print(f'[{i+1}/{len(tasks)}] {task["id"]}: {task["title"][:40]}...', end=" ", flush=True)
        r = await run_task_with_loop(task, model='deepseek-chat')
        mark = 'PASS' if r.passed else 'FAIL'
        elapsed = round(time.time() - task_start, 1)
        print(f'{mark} ({elapsed}s)')
        if not r.passed:
            print(f'  -> {r.details[:100]}')
        results.append(r)

    report = build_report(results)
    rd = asdict(report)

    report_path = 'D:/codex-local/data/eval/reports/eval-honest-v3.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(rd, f, indent=2, ensure_ascii=False)

    print(f'\n{"="*60}')
    print(f'  HONEST EVAL RESULTS')
    print(f'{"="*60}')
    print(f'  Total: {rd["total_tasks"]}')
    print(f'  Passed: {rd["passed"]}')
    print(f'  Failed: {rd["failed"]}')
    print(f'  Pass Rate: {rd["pass_rate"]}%')
    print()

    print('  By Category:')
    for cat, stats in sorted(rd['by_category'].items()):
        print(f'    {cat:15s} {stats["passed"]}/{stats["total"]} ({stats["pass_rate"]}%)')

    print()
    print('  By Difficulty:')
    for diff, stats in sorted(rd['by_difficulty'].items()):
        print(f'    {diff:15s} {stats["passed"]}/{stats["total"]} ({stats["pass_rate"]}%)')

    failures = [r for r in rd['results'] if not r['passed']]
    if failures:
        print(f'\n  Failed Tasks ({len(failures)}):')
        for fail in failures:
            print(f'    [{fail["task_id"]}] {fail["title"]}')
            print(f'      Category: {fail["category"]} | Difficulty: {fail["difficulty"]}')
            print(f'      Details: {fail.get("details","")[:100]}')

    print(f'\n  Report saved to: {report_path}')
    print(f'  End time: {time.strftime("%Y-%m-%d %H:%M:%S")}')

if __name__ == "__main__":
    asyncio.run(main())
