"""
真正的自我进化循环

不是空转，是：
  做真实任务 → 真实失败 → 分析真实原因 → 真实改进 → 再做 → 更好

用法：
    python scripts/real_evolution.py
    python scripts/real_evolution.py --cycles 3
    python scripts/real_evolution.py --category bugfix
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.eval.run_eval import load_tasks, run_task_with_loop, build_report


async def run_eval(model: str, tasks: list = None) -> dict:
    """跑一次真实 eval，返回结果"""
    if tasks is None:
        tasks = load_tasks()

    results = []
    for task in tasks:
        r = await run_task_with_loop(task, model=model)
        results.append(r)

    report = build_report(results)
    return {
        "passed": sum(1 for r in results if r.passed),
        "total": len(results),
        "rate": report.pass_rate,
        "failures": [
            {"id": r.task_id, "title": r.title, "error": r.details}
            for r in results if not r.passed
        ],
        "results": results,
    }


async def analyze_failure(task: dict, error: str, model: str) -> str:
    """用 LLM 分析失败原因"""
    from runtime.loop import CodexLoop, LoopConfig

    prompt = f"""分析这个任务为什么失败，给出修复建议。

任务：{task['title']}
类别：{task['category']}
描述：{task['task']}
错误：{error}

只输出一句话：失败的根本原因和修复方法。"""

    config = LoopConfig(model=model, max_iterations=3)
    loop = CodexLoop(config)
    result = await loop.run_task(prompt)
    return result


async def fix_task(task: dict, error: str, model: str) -> bool:
    """让 LLM 修复失败的任务"""
    from runtime.loop import CodexLoop, LoopConfig

    prompt = f"""修复这个失败的任务。

任务：{task['task']}
错误：{error}

规则：
1. 先读相关文件
2. 找到问题
3. 用 Edit 修复
4. 用 Bash 验证
5. 不要描述，直接做"""

    config = LoopConfig(model=model, max_iterations=15)
    loop = CodexLoop(config)
    result = await loop.run_task(prompt)
    return "completed" in result.lower()


async def verify_fix(task: dict) -> bool:
    """验证修复是否成功"""
    from data.eval.run_eval import verify_task
    passed, _ = verify_task(task)
    return passed


async def evolve_cycle(cycle: int, model: str, category: str = None) -> dict:
    """一轮真正的进化"""
    print(f"\n{'='*50}")
    print(f"  Evolution Cycle {cycle}")
    print(f"{'='*50}")

    # Step 1: 跑 eval
    print(f"\n[1/5] Running eval...")
    tasks = load_tasks()
    if category:
        tasks = [t for t in tasks if t["category"] == category]

    eval_result = await run_eval(model, tasks)
    print(f"  Result: {eval_result['passed']}/{eval_result['total']} ({eval_result['rate']}%)")

    if not eval_result["failures"]:
        print("  All tasks passing! No evolution needed.")
        return {"cycle": cycle, "improved": False, "reason": "all_passing"}

    # Step 2: 分析失败
    print(f"\n[2/5] Analyzing {len(eval_result['failures'])} failures...")
    analyses = {}
    for fail in eval_result["failures"]:
        print(f"  {fail['id']}: {fail['title'][:40]}...")
        analysis = await analyze_failure(
            {"title": fail["title"], "category": "", "task": fail.get("error", "")},
            fail.get("error", ""),
            model
        )
        analyses[fail["id"]] = analysis
        print(f"    -> {analysis[:60]}")

    # Step 3: 修复失败任务
    print(f"\n[3/5] Fixing failures...")
    fixed = []
    for fail in eval_result["failures"]:
        task = next((t for t in tasks if t["id"] == fail["id"]), None)
        if not task:
            continue

        print(f"  Fixing {fail['id']}...")
        success = await fix_task(task, fail.get("error", ""), model)
        if success:
            fixed.append(fail["id"])
            print(f"    -> Fixed")
        else:
            print(f"    -> Failed to fix")

    # Step 4: 验证修复
    print(f"\n[4/5] Verifying fixes...")
    verified = []
    for task_id in fixed:
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            continue

        passed = await verify_fix(task)
        if passed:
            verified.append(task_id)
            print(f"  {task_id}: PASS")
        else:
            print(f"  {task_id}: FAIL")

    # Step 5: 记录结果
    print(f"\n[5/5] Recording results...")
    result = {
        "cycle": cycle,
        "before": eval_result["rate"],
        "failures": len(eval_result["failures"]),
        "fixed": len(fixed),
        "verified": len(verified),
        "improved": len(verified) > 0,
    }

    # 保存经验
    lessons_file = ROOT / "data" / "eval" / "lessons.json"
    lessons = []
    if lessons_file.exists():
        lessons = json.loads(lessons_file.read_text(encoding="utf-8"))

    for fail in eval_result["failures"]:
        if fail["id"] in verified:
            lessons.append({
                "id": f"lesson-{fail['id']}-cycle{cycle}",
                "pattern": f"Task {fail['id']} failed: {fail.get('error', '')[:80]}",
                "fix": analyses.get(fail["id"], "Fixed by LLM"),
                "category": fail.get("category", "unknown"),
                "source_task": fail["id"],
                "confidence": 0.8,
                "times_applied": 0,
                "times_successful": 0,
                "created_at": time.strftime("%Y-%m-%d"),
            })

    lessons_file.write_text(json.dumps(lessons, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Lessons: {len(lessons)} total")

    # 打印总结
    print(f"\n{'='*50}")
    print(f"  Cycle {cycle} Summary")
    print(f"{'='*50}")
    print(f"  Before:     {eval_result['rate']}%")
    print(f"  Failures:   {len(eval_result['failures'])}")
    print(f"  Fixed:      {len(fixed)}")
    print(f"  Verified:   {len(verified)}")
    print(f"  Improved:   {'Yes' if result['improved'] else 'No'}")

    return result


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--category", default=None)
    parser.add_argument("--model", default="deepseek-chat")
    args = parser.parse_args()

    os.environ["DEEPSEEK_API_KEY"] = "sk-842a3aa4bbcb482a89482585aa227171"

    print("Real Evolution Loop")
    print(f"Model: {args.model}")
    print(f"Cycles: {args.cycles}")
    if args.category:
        print(f"Category: {args.category}")

    results = []
    for cycle in range(1, args.cycles + 1):
        result = await evolve_cycle(cycle, args.model, args.category)
        results.append(result)

        if not result.get("improved"):
            print(f"\nNo improvement in cycle {cycle}. Stopping.")
            break

    # 最终报告
    print(f"\n{'='*50}")
    print(f"  Final Report")
    print(f"{'='*50}")
    for r in results:
        print(f"  Cycle {r['cycle']}: {r['before']}% -> {r.get('after', r['before'])}% | "
              f"Fixed: {r.get('fixed', 0)} | Verified: {r.get('verified', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
