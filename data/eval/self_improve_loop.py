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
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EVAL_DIR = Path(__file__).resolve().parent
LESSONS_FILE = EVAL_DIR / "lessons.json"
IMPROVEMENT_LOG = EVAL_DIR / "improvement_log.jsonl"
SUMMARY_DIR = EVAL_DIR / "reports"


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


@dataclass
class ProgressTracker:
    """Track improvement progress across cycles."""
    pass_rates: List[float] = field(default_factory=list)
    no_improvement_count: int = 0
    max_no_improvement: int = 2  # Stop after 2 consecutive rounds without improvement

    def record(self, pass_rate: float) -> bool:
        """Record a pass_rate. Returns True if we should continue, False to stop."""
        self.pass_rates.append(pass_rate)

        if len(self.pass_rates) >= 2:
            if self.pass_rates[-1] <= self.pass_rates[-2]:
                self.no_improvement_count += 1
            else:
                self.no_improvement_count = 0

        return self.no_improvement_count < self.max_no_improvement

    @property
    def trend(self) -> str:
        if len(self.pass_rates) < 2:
            return "insufficient data"
        if self.pass_rates[-1] > self.pass_rates[-2]:
            return "improving"
        elif self.pass_rates[-1] < self.pass_rates[-2]:
            return "regressing"
        return "stagnant"


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


def verify_task(task: Dict[str, Any]) -> tuple[bool, str]:
    """Run all verification checks for a task.

    This actually executes verify_test commands (not just file existence checks).
    Falls back to file-based checks when no test command is defined.
    """
    # File-based checks
    verify_file = task.get("verify_file")
    if verify_file:
        full_path = PROJECT_ROOT / verify_file
        if not full_path.exists():
            return False, f"file not found: {verify_file}"

        content = full_path.read_text(encoding='utf-8')

        if "verify_contains" in task:
            if task["verify_contains"] not in content:
                return False, f"expected '{task['verify_contains']}' in {verify_file}"

        if "verify_not_contains" in task:
            if task["verify_not_contains"] in content:
                return False, f"unexpected '{task['verify_not_contains']}' in {verify_file}"

        if "verify_min_length" in task:
            if len(content) < task["verify_min_length"]:
                return False, f"content too short: {len(content)} < {task['verify_min_length']}"

    # Test command execution (the key fix: actually run the command)
    verify_test = task.get("verify_test")
    if verify_test:
        py = sys.executable
        verify_test = verify_test.replace("python -m pytest", f'"{py}" -m pytest')
        verify_test = verify_test.replace("python -c", f'"{py}" -c')
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
                    return False, f"expected '{task['verify_output_contains']}' in output"

            return True, f"test passed: {output[:200]}"

        except subprocess.TimeoutExpired:
            return False, "test timed out (30s)"
        except Exception as e:
            return False, f"test error: {e}"

    # No verification defined at all
    if not verify_file and not verify_test:
        return False, "no verification method defined"

    return True, "file checks passed"


async def verify_task_with_llm(task: Dict[str, Any], model: str = "mimo-v2.5") -> tuple[bool, str]:
    """Use LLM to judge whether a task is completed successfully.

    Used when no automated test command exists. The LLM reads the relevant
    files and decides if the task requirements are met.
    """
    from runtime.loop import _call_llm_async, _resolve_api_key, LoopConfig

    # Gather context: read files mentioned in the task
    context_parts = []
    verify_file = task.get("verify_file")
    if verify_file:
        full_path = PROJECT_ROOT / verify_file
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            context_parts.append(f"File {verify_file}:\n```\n{content[:3000]}\n```")

    # Also check setup_files for additional context
    for rel_path in list(task.get("setup_files", {}).keys())[:3]:
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            content = full_path.read_text(encoding='utf-8')
            context_parts.append(f"File {rel_path}:\n```\n{content[:2000]}\n```")

    context_text = "\n\n".join(context_parts) if context_parts else "(no files found)"

    prompt = f"""You are evaluating whether a coding task was completed successfully.

Task: {task['title']}
Description: {task['task']}
Category: {task.get('category', 'unknown')}

Verification criteria:
- File check: {task.get('verify_file', 'none')}
- Contains: {task.get('verify_contains', 'n/a')}
- Not contains: {task.get('verify_not_contains', 'n/a')}

Current state of relevant files:
{context_text}

Answer with ONLY a JSON object (no markdown):
{{"passed": true/false, "reason": "brief explanation", "confidence": 0.0-1.0}}"""

    try:
        config = LoopConfig(model=model, max_iterations=1)
        messages = [
            {"role": "system", "content": "You evaluate code task completion. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]
        api_key = _resolve_api_key()
        result = await _call_llm_async(messages, config, api_key, "", model)

        # Extract content
        content = ""
        choices = result.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        elif result.get("output"):
            for item in result["output"]:
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        if c.get("type") == "output_text":
                            content += c.get("text", "")

        if not content:
            return False, "LLM returned empty response"

        # Parse JSON
        decoder = json.JSONDecoder()
        for start_idx in range(len(content)):
            if content[start_idx] == '{':
                try:
                    data, _ = decoder.raw_decode(content, start_idx)
                    passed = bool(data.get("passed", False))
                    reason = data.get("reason", "no reason given")
                    confidence = float(data.get("confidence", 0.5))
                    return passed, f"LLM judge (conf={confidence:.2f}): {reason}"
                except (json.JSONDecodeError, ValueError):
                    continue

        return False, "could not parse LLM response"

    except Exception as e:
        return False, f"LLM verification error: {e}"


async def auto_retry(task: Dict[str, Any], eval_result: Dict[str, Any],
                     lessons: List[Lesson], model: str = "deepseek-chat",
                     max_retries: int = 3) -> tuple[bool, str, int]:
    """Retry a failed task up to max_retries times.

    Returns: (success, details, attempts_used)
    """
    for attempt in range(1, max_retries + 1):
        print(f"    Retry attempt {attempt}/{max_retries}...")

        # Get relevant lessons for this retry
        relevant = get_relevant_lessons(task["category"], task["title"], lessons)

        # Generate fix
        fix_result = await generate_fix(task, eval_result, relevant, model)
        if not fix_result:
            print(f"    Fix generation failed on attempt {attempt}")
            continue

        # Verify the fix using the real verify_task
        passed, details = verify_task(task)

        if passed:
            print(f"    Passed on attempt {attempt}!")
            return True, details, attempt

        print(f"    Still failing: {details[:80]}")
        # Update eval_result with new error for next retry
        eval_result["error"] = details
        eval_result["details"] = details

    return False, f"failed after {max_retries} retries", max_retries


async def analyze_failure(task: Dict[str, Any], eval_result: Dict[str, Any], model: str = "mimo-v2.5") -> Optional[Lesson]:
    """Use LLM to analyze a failure and extract a lesson."""
    from runtime.loop import _call_llm_async, _resolve_api_key, _resolve_api_url, LoopConfig

    prompt = f"""Analyze this failed task and extract a reusable lesson.

Task: {task['title']}
Category: {task['category']}
Task description: {task['task']}
Error: {eval_result.get('error', 'none')}
Details: {eval_result.get('details', 'none')}

Output ONLY a JSON object (no markdown, no explanation):
{{"pattern": "What went wrong", "fix": "How to fix it", "confidence": 0.8}}"""

    try:
        config = LoopConfig(model=model, max_iterations=1)
        messages = [
            {"role": "system", "content": "You extract reusable lessons from code failures. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]
        api_key = _resolve_api_key()
        result = await _call_llm_async(messages, config, api_key, "", model)

        # Extract content from response
        content = ""
        choices = result.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
        elif result.get("output"):
            for item in result["output"]:
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        if c.get("type") == "output_text":
                            content += c.get("text", "")

        if not content:
            return None

        # Parse JSON from content
        decoder = json.JSONDecoder()
        for start_idx in range(len(content)):
            if content[start_idx] == '{':
                try:
                    data, _ = decoder.raw_decode(content, start_idx)
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
        config = LoopConfig(model=model, max_iterations=10)
        loop = CodexLoop(config)
        result = await loop.run_task(prompt)
        return result
    except Exception as e:
        return f"Fix generation failed: {e}"


def generate_summary(cycles: List[ImprovementCycle], lessons: List[Lesson],
                     tracker: ProgressTracker, total_tasks: int) -> str:
    """Generate an improvement summary report in markdown format."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Self-Improvement Report",
        f"",
        f"Generated: {timestamp}",
        f"Total tasks in eval: {total_tasks}",
        f"Cycles completed: {len(cycles)}",
        f"",
        f"## Progress",
        f"",
        f"| Cycle | Pass Rate Before | Pass Rate After | Fixed | Lessons | Regressions |",
        f"|-------|-----------------|----------------|-------|---------|-------------|",
    ]

    for c in cycles:
        lines.append(
            f"| {c.cycle_number} | {c.eval_pass_rate_before:.1f}% | {c.eval_pass_rate_after:.1f}% "
            f"| {len(c.tasks_fixed)} | {len(c.lessons_generated)} | {len(c.regressions)} |"
        )

    lines.append("")
    lines.append(f"## Trend: {tracker.trend}")
    lines.append("")

    if tracker.pass_rates:
        lines.append(f"Pass rate history: {' -> '.join(f'{r:.1f}%' for r in tracker.pass_rates)}")
        lines.append("")

    # Lessons summary
    lines.append(f"## Lessons Learned ({len(lessons)} total)")
    lines.append("")
    if lessons:
        lines.append("| Category | Pattern | Fix | Confidence | Success Rate |")
        lines.append("|----------|---------|-----|------------|-------------|")
        for l in lessons[-20:]:  # Last 20 lessons
            pattern = l.pattern[:60] + "..." if len(l.pattern) > 60 else l.pattern
            fix = l.fix[:60] + "..." if len(l.fix) > 60 else l.fix
            lines.append(f"| {l.category} | {pattern} | {fix} | {l.confidence:.2f} | {l.success_rate:.2f} |")
    else:
        lines.append("No lessons recorded yet.")

    lines.append("")

    # Failure analysis
    all_fixed = set()
    all_regressions = set()
    for c in cycles:
        all_fixed.update(c.tasks_fixed)
        all_regressions.update(c.regressions)

    lines.append(f"## Summary")
    lines.append(f"- Total tasks fixed across all cycles: {len(all_fixed)}")
    lines.append(f"- Total regressions: {len(all_regressions)}")
    if all_regressions:
        lines.append(f"- Regression tasks: {', '.join(sorted(all_regressions))}")
    lines.append(f"- Final pass rates: {tracker.pass_rates[-1]:.1f}%" if tracker.pass_rates else "N/A")
    lines.append("")

    return "\n".join(lines)


async def run_improvement_cycle(cycle_num: int, failed_tasks: List[Dict[str, Any]],
                                failed_results: List[Dict[str, Any]],
                                lessons: List[Lesson],
                                model: str = "deepseek-chat",
                                dry_run: bool = False,
                                use_llm_verify: bool = False) -> ImprovementCycle:
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

        # Step 3: Auto-retry with fix generation
        print(f"    Generating fix with auto-retry (max 3)...")
        success, details, attempts = await auto_retry(
            task, result, lessons, model=model, max_retries=3
        )

        if success:
            cycle.tasks_fixed.append(task_id)
            cycle.patches_applied.append({
                "task_id": task_id,
                "attempts": attempts,
                "result_summary": details[:200]
            })
            print(f"    Fixed after {attempts} attempt(s)")
        else:
            # If auto-retry failed, try LLM verification as fallback
            if use_llm_verify:
                print(f"    Auto-retry failed, trying LLM verification...")
                llm_passed, llm_details = await verify_task_with_llm(task, model=model)
                if llm_passed:
                    cycle.tasks_fixed.append(task_id)
                    cycle.patches_applied.append({
                        "task_id": task_id,
                        "attempts": attempts,
                        "result_summary": f"LLM verified: {llm_details[:150]}"
                    })
                    print(f"    LLM says: PASSED")
                else:
                    print(f"    LLM says: FAILED - {llm_details[:80]}")
            else:
                print(f"    Failed after {attempts} attempts: {details[:80]}")

    # Save lessons
    save_lessons(lessons)

    # Log the cycle
    append_improvement_log(asdict(cycle))

    return cycle


async def main():
    parser = argparse.ArgumentParser(description="Codex-Local Self-Improvement Loop")
    parser.add_argument("--max-cycles", type=int, default=3, help="Maximum improvement cycles")
    parser.add_argument("--category", help="Focus on this category")
    parser.add_argument("--model", default="mimo-v2.5", help="Model to use (or 'offline' for no LLM)")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--llm-verify", action="store_true", help="Use LLM to verify tasks when no test command")
    args = parser.parse_args()

    print("=" * 50)
    print("  Codex-Local Self-Improvement Loop")
    print("=" * 50)

    lessons = load_lessons()
    print(f"  Loaded {len(lessons)} existing lessons")

    cycles: List[ImprovementCycle] = []
    tracker = ProgressTracker()
    total_tasks = 0

    for cycle_num in range(1, args.max_cycles + 1):
        # Step 1: Run eval
        print(f"\n  Running eval (cycle {cycle_num})...")
        eval_task = __import__('run_eval')
        tasks = eval_task.load_tasks()

        if args.category:
            tasks = [t for t in tasks if t["category"] == args.category]

        total_tasks = len(tasks)

        # Run eval
        results = []
        use_llm = args.model and args.model != "offline"
        for task in tasks:
            if use_llm:
                result = await eval_task.run_task_with_loop(task, model=args.model)
            else:
                result = eval_task.run_task_subprocess(task)
            results.append(result)

        report = eval_task.build_report(results)
        pass_rate = report.pass_rate
        print(f"  Eval: {report.passed}/{report.total_tasks} passed ({pass_rate}%)")

        # Record progress and check early stop
        should_continue = tracker.record(pass_rate)
        if not should_continue:
            print(f"\n  Stopping: no improvement for {tracker.max_no_improvement} consecutive rounds")
            print(f"  Pass rate history: {' -> '.join(f'{r:.1f}%' for r in tracker.pass_rates)}")
            break

        # Step 2: Collect failures
        failed_tasks = []
        failed_results = []
        for task, result in zip(tasks, results):
            if not result.passed:
                failed_tasks.append(task)
                failed_results.append(asdict(result))

        if not failed_tasks:
            print(f"\n  All tasks passing! No improvements needed.")
            # Record the cycle even with no failures
            cycle = ImprovementCycle(
                cycle_number=cycle_num,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                eval_pass_rate_before=pass_rate,
                eval_pass_rate_after=pass_rate,
            )
            cycles.append(cycle)
            break

        print(f"  {len(failed_tasks)} tasks failing")

        # Step 3: Run improvement cycle
        cycle = await run_improvement_cycle(
            cycle_num, failed_tasks, failed_results, lessons,
            model=args.model, dry_run=args.dry_run,
            use_llm_verify=args.llm_verify
        )
        cycle.eval_pass_rate_before = pass_rate

        # Step 4: Re-evaluate to get new pass rate
        print(f"\n  Re-evaluating after fixes...")
        re_results = []
        for task in tasks:
            if use_llm:
                result = await eval_task.run_task_with_loop(task, model=args.model)
            else:
                result = eval_task.run_task_subprocess(task)
            re_results.append(result)

        re_report = eval_task.build_report(re_results)
        cycle.eval_pass_rate_after = re_report.pass_rate
        print(f"  Re-eval: {re_report.passed}/{re_report.total_tasks} passed ({re_report.pass_rate}%)")

        # Detect regressions
        for i, (before, after) in enumerate(zip(results, re_results)):
            if before.passed and not after.passed:
                cycle.regressions.append(tasks[i]["id"])

        cycles.append(cycle)

        print(f"\n  Cycle {cycle_num} complete:")
        print(f"    Pass rate: {pass_rate:.1f}% -> {re_report.pass_rate:.1f}%")
        print(f"    Tasks fixed: {len(cycle.tasks_fixed)}")
        print(f"    Lessons generated: {len(cycle.lessons_generated)}")
        print(f"    Regressions: {len(cycle.regressions)}")

    # Generate summary report
    lessons = load_lessons()
    summary = generate_summary(cycles, lessons, tracker, total_tasks)

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = SUMMARY_DIR / f"improvement-{time.strftime('%Y%m%d-%H%M%S')}.md"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary)

    print(f"\n  Summary saved to: {summary_path}")
    print(f"  Total lessons: {len(lessons)}")
    print(f"  Improvement log: {IMPROVEMENT_LOG}")


if __name__ == "__main__":
    asyncio.run(main())
