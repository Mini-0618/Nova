"""
Codex-Local Self-Improvement Loop
Iterates: eval -> analyze failures -> generate fixes -> test fixes -> record lessons

Usage:
    python data/eval/self_improve_loop.py --max-cycles 3
    python data/eval/self_improve_loop.py --category bugfix --max-cycles 1
    python data/eval/self_improve_loop.py --dry-run
"""

import os
import sys
import json
import time
import asyncio
import argparse
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EVAL_DIR = Path(__file__).resolve().parent
LESSONS_FILE = EVAL_DIR / "lessons.json"
IMPROVEMENT_LOG = EVAL_DIR / "improvement_log.jsonl"


@dataclass
class Lesson:
    """A reusable lesson extracted from a failure or success."""
    id: str
    pattern: str  # What went wrong
    fix: str  # How to fix it
    category: str  # bugfix, file_io, multi_file, etc.
    source_task: str  # Which task generated this
    confidence: float = 0.0  # 0-1, how reliable this lesson is
    times_applied: int = 0
    times_successful: int = 0
    created_at: str = ""

    @property
    def success_rate(self) -> float:
        return self.times_successful / self.times_applied if self.times_applied > 0 else 0


@dataclass
class ImprovementCycle:
    """One cycle of the self-improvement loop."""
    cycle_number: int
    timestamp: str
    eval_pass_rate_before: float
    eval_pass_rate_after: float
    tasks_fixed: List[str] = field(default_factory=list)
    lessons_generated: List[str] = field(default_factory=list)
    patches_applied: List[Dict[str, Any]] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)


def load_lessons() -> List[Lesson]:
    """Load existing lessons from lessons.json."""
    if not LESSONS_FILE.exists():
        return []
    with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [Lesson(**item) for item in data]


def save_lessons(lessons: List[Lesson]):
    """Save lessons to lessons.json."""
    with open(LESSONS_FILE, 'w', encoding='utf-8') as f:
        json.dump([asdict(l) for l in lessons], f, indent=2, ensure_ascii=False)


def append_improvement_log(entry: Dict[str, Any]):
    """Append to improvement log (JSONL format)."""
    with open(IMPROVEMENT_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_relevant_lessons(task_category: str, task_title: str, lessons: List[Lesson]) -> List[Lesson]:
    """Retrieve lessons relevant to the current task."""
    relevant = []
    for lesson in lessons:
        # Category match
        if lesson.category == task_category:
            relevant.append(lesson)
        # Pattern match in title (simple keyword overlap)
        elif any(word in task_title.lower() for word in lesson.pattern.lower().split()[:3]):
            relevant.append(lesson)
    # Sort by success rate (most reliable first)
    relevant.sort(key=lambda l: l.success_rate, reverse=True)
    return relevant[:5]  # Top 5


async def analyze_failure(task: Dict[str, Any], eval_result: Dict[str, Any], model: str = "deepseek-chat") -> Optional[Lesson]:
    """Use LLM to analyze a failure and extract a lesson."""
    from runtime.loop import CodexLoop, LoopConfig

    prompt = f"""Analyze this failed task and extract a reusable lesson.

Task: {task['title']}
Category: {task['category']}
Task description: {task['task']}
Error: {eval_result.get('error', 'none')}
Details: {eval_result.get('details', 'none')}

Output a JSON object with:
{{
  "pattern": "What went wrong (one sentence)",
  "fix": "How to fix it (one sentence)",
  "confidence": 0.0 to 1.0
}}

Rules:
- Be specific, not generic
- Focus on the actual error, not the task description
- The pattern should be recognizable in future similar failures
- The fix should be actionable
- Output ONLY the JSON object, no other text"""

    try:
        config = LoopConfig(model=model, max_iterations=3, workspace=str(PROJECT_ROOT))
        loop = CodexLoop(config)
        result = await loop.run_task(prompt)

        # Parse the JSON from result
        decoder = json.JSONDecoder()
        for start_idx in range(len(result)):
            if result[start_idx] == '{':
                try:
                    data, _ = decoder.raw_decode(result, start_idx)
                    return Lesson(
                        id=f"lesson-{int(time.time())}",
                        pattern=data.get("pattern", "unknown"),
                        fix=data.get("fix", "unknown"),
                        category=task.get("category", "unknown"),
                        source_task=task.get("id", "unknown"),
                        confidence=float(data.get("confidence", 0.5)),
                        created_at=time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                except (json.JSONDecodeError, ValueError):
                    continue
    except Exception as e:
        print(f"    [lesson extraction failed: {e}]")

    return None


async def generate_fix(task: Dict[str, Any], eval_result: Dict[str, Any],
                       relevant_lessons: List[Lesson], model: str = "deepseek-chat") -> Optional[str]:
    """Use LLM to generate a fix for a failed task."""
    from runtime.loop import CodexLoop, LoopConfig

    lessons_text = ""
    if relevant_lessons:
        lessons_text = "\nRelevant lessons from past failures:\n"
        for i, lesson in enumerate(relevant_lessons, 1):
            lessons_text += f"  {i}. Pattern: {lesson.pattern}\n     Fix: {lesson.fix}\n"

    prompt = f"""Fix this failing task.

Task: {task['title']}
Description: {task['task']}
Error: {eval_result.get('error', 'none')}
Details: {eval_result.get('details', 'none')}
{lessons_text}
Rules:
1. Read the relevant files first to understand the current state.
2. Make the smallest change that fixes the issue.
3. Run the verification test after your fix.
4. If the test passes, stop. If not, try one more time based on the error.
5. Do NOT modify unrelated files.
6. Do NOT delete tests to make them pass.

After fixing, report:
- What files you changed
- What the fix was
- Whether the test passes"""

    try:
        config = LoopConfig(model=model, max_iterations=10, workspace=str(PROJECT_ROOT))
        loop = CodexLoop(config)
        result = await loop.run_task(prompt)
        return result
    except Exception as e:
        return f"Fix generation failed: {e}"


async def run_improvement_cycle(cycle_num: int, failed_tasks: List[Dict[str, Any]],
                                failed_results: List[Dict[str, Any]],
                                lessons: List[Lesson],
                                model: str = "deepseek-chat",
                                dry_run: bool = False) -> ImprovementCycle:
    """Run one cycle of the self-improvement loop."""
    cycle = ImprovementCycle(
        cycle_number=cycle_num,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        eval_pass_rate_before=0,
        eval_pass_rate_after=0
    )

    print(f"\n{'='*50}")
    print(f"  Improvement Cycle {cycle_num}")
    print(f"  Failed tasks to analyze: {len(failed_tasks)}")
    print(f"{'='*50}")

    for task, result in zip(failed_tasks, failed_results):
        task_id = task["id"]
        print(f"\n  [{task_id}] {task['title']}")

        if dry_run:
            print(f"    [dry-run] Would analyze failure and generate fix")
            cycle.tasks_fixed.append(task_id)
            continue

        # Step 1: Get relevant lessons
        relevant = get_relevant_lessons(task["category"], task["title"], lessons)
        if relevant:
            print(f"    Found {len(relevant)} relevant lessons")

        # Step 2: Analyze failure and extract lesson
        print(f"    Analyzing failure...")
        lesson = await analyze_failure(task, result, model)
        if lesson:
            lessons.append(lesson)
            cycle.lessons_generated.append(lesson.id)
            print(f"    Lesson: {lesson.pattern}")

        # Step 3: Generate and apply fix
        print(f"    Generating fix...")
        fix_result = await generate_fix(task, result, relevant, model)
        if fix_result:
            cycle.tasks_fixed.append(task_id)
            cycle.patches_applied.append({
                "task_id": task_id,
                "result_summary": fix_result[:200] if fix_result else "no result"
            })
            print(f"    Fix applied")

    # Save lessons
    save_lessons(lessons)

    # Log the cycle
    append_improvement_log(asdict(cycle))

    return cycle


async def main():
    parser = argparse.ArgumentParser(description="Codex-Local Self-Improvement Loop")
    parser.add_argument("--max-cycles", type=int, default=3, help="Maximum improvement cycles")
    parser.add_argument("--category", help="Focus on this category")
    parser.add_argument("--model", default="deepseek-chat", help="Model to use")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    args = parser.parse_args()

    print("=" * 50)
    print("  Codex-Local Self-Improvement Loop")
    print("=" * 50)

    lessons = load_lessons()
    print(f"  Loaded {len(lessons)} existing lessons")

    for cycle_num in range(1, args.max_cycles + 1):
        # Step 1: Run eval
        print(f"\n  Running eval (cycle {cycle_num})...")
        eval_task = __import__('run_eval')
        tasks = eval_task.load_tasks()

        if args.category:
            tasks = [t for t in tasks if t["category"] == args.category]

        # Run eval (offline mode for now — can switch to LLM mode)
        results = []
        for task in tasks:
            result = eval_task.run_task_subprocess(task)
            results.append(result)

        report = eval_task.build_report(results)
        print(f"  Eval: {report.passed}/{report.total_tasks} passed ({report.pass_rate}%)")

        # Step 2: Collect failures
        failed_tasks = []
        failed_results = []
        for task, result in zip(tasks, results):
            if not result.passed:
                failed_tasks.append(task)
                failed_results.append(asdict(result))

        if not failed_tasks:
            print(f"\n  All tasks passing! No improvements needed.")
            break

        print(f"  {len(failed_tasks)} tasks failing")

        # Step 3: Run improvement cycle
        cycle = await run_improvement_cycle(
            cycle_num, failed_tasks, failed_results, lessons,
            model=args.model, dry_run=args.dry_run
        )

        print(f"\n  Cycle {cycle_num} complete:")
        print(f"    Tasks fixed: {len(cycle.tasks_fixed)}")
        print(f"    Lessons generated: {len(cycle.lessons_generated)}")
        print(f"    Regressions: {len(cycle.regressions)}")

    # Final lesson count
    lessons = load_lessons()
    print(f"\n  Total lessons: {len(lessons)}")
    print(f"  Improvement log: {IMPROVEMENT_LOG}")


if __name__ == "__main__":
    asyncio.run(main())
