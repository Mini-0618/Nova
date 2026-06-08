"""
Auto Lesson Extractor
Reads eval report JSON, analyzes failures with LLM, appends lessons to lessons.json.

Usage:
    python data/eval/auto_lessons.py data/eval/reports/eval-20260609-0300.json
    python data/eval/auto_lessons.py --latest
    python data/eval/auto_lessons.py --latest --dry-run
"""

import json
import sys
import time
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

EVAL_DIR = Path(__file__).resolve().parent
LESSONS_FILE = EVAL_DIR / "lessons.json"
REPORTS_DIR = EVAL_DIR / "reports"


def load_lessons() -> List[Dict[str, Any]]:
    """Load existing lessons from lessons.json."""
    if not LESSONS_FILE.exists():
        return []
    with open(LESSONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_lessons(lessons: List[Dict[str, Any]]) -> None:
    """Save lessons to lessons.json."""
    with open(LESSONS_FILE, "w", encoding="utf-8") as f:
        json.dump(lessons, f, indent=2, ensure_ascii=False)


def lesson_exists(lessons: List[Dict[str, Any]], pattern: str) -> bool:
    """Check if a lesson with similar pattern already exists."""
    pattern_lower = pattern.lower().strip()
    for l in lessons:
        existing = l.get("pattern", "").lower().strip()
        # Exact match or high overlap
        if existing == pattern_lower:
            return True
        # Check if first 50 chars match (fuzzy dedup)
        if len(pattern_lower) > 20 and len(existing) > 20:
            if pattern_lower[:50] == existing[:50]:
                return True
    return False


async def analyze_failure_with_llm(
    task: Dict[str, Any],
    model: str = "mimo-v2.5",
) -> Optional[Dict[str, Any]]:
    """Use LLM to analyze a failed task and extract a lesson."""
    try:
        from runtime.loop import _call_llm_async, _resolve_api_key, LoopConfig
    except ImportError:
        print("  [warn] Cannot import runtime.loop, skipping LLM analysis")
        return None

    prompt = f"""Analyze this failed coding task and extract a reusable lesson.

Task ID: {task.get('task_id', 'unknown')}
Title: {task.get('title', 'unknown')}
Category: {task.get('category', 'unknown')}
Difficulty: {task.get('difficulty', 'unknown')}
Error: {task.get('error', 'none')}
Details: {task.get('details', 'none')}

Output ONLY a JSON object (no markdown, no explanation):
{{"pattern": "What went wrong (specific, actionable)", "fix": "How to prevent/fix it", "confidence": 0.8}}"""

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
            if content[start_idx] == "{":
                try:
                    data, _ = decoder.raw_decode(content, start_idx)
                    return {
                        "pattern": data.get("pattern", "unknown"),
                        "fix": data.get("fix", "unknown"),
                        "confidence": float(data.get("confidence", 0.5)),
                    }
                except (json.JSONDecodeError, ValueError):
                    continue

    except Exception as e:
        print(f"  [warn] LLM analysis failed: {e}")

    return None


def make_lesson_from_analysis(
    task: Dict[str, Any],
    analysis: Dict[str, Any],
    existing_count: int,
) -> Dict[str, Any]:
    """Create a lesson dict from LLM analysis result."""
    task_id = task.get("task_id", "unknown")
    return {
        "id": f"lesson-auto-{task_id}-{int(time.time())}",
        "pattern": analysis["pattern"],
        "fix": analysis["fix"],
        "category": task.get("category", "unknown"),
        "source_task": task_id,
        "confidence": analysis.get("confidence", 0.5),
        "times_applied": 0,
        "times_successful": 0,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "auto_lessons",
    }


async def extract_lessons_from_report(
    report_path: str,
    model: str = "mimo-v2.5",
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Read an eval report, analyze failures, generate lessons.

    Returns list of newly added lessons.
    """
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed")]

    if not failures:
        print("  No failures to analyze.")
        return []

    print(f"  Analyzing {len(failures)} failures...")

    lessons = load_lessons()
    new_lessons = []

    for i, failure in enumerate(failures, 1):
        task_id = failure.get("task_id", "?")
        title = failure.get("title", "?")[:60]
        print(f"  [{i}/{len(failures)}] {task_id}: {title}...", end=" ", flush=True)

        # Skip if we already have a lesson for this exact pattern
        error_detail = failure.get("error", "") or failure.get("details", "")
        if lesson_exists(lessons, error_detail):
            print("skip (duplicate)")
            continue

        if dry_run:
            print("dry-run (would analyze)")
            continue

        analysis = await analyze_failure_with_llm(failure, model=model)
        if not analysis:
            print("no analysis")
            continue

        if lesson_exists(lessons, analysis["pattern"]):
            print("skip (duplicate pattern)")
            continue

        lesson = make_lesson_from_analysis(failure, analysis, len(lessons))
        new_lessons.append(lesson)
        lessons.append(lesson)
        print(f"lesson: {analysis['pattern'][:50]}...")

    if new_lessons and not dry_run:
        save_lessons(lessons)
        print(f"\n  Saved {len(new_lessons)} new lessons to {LESSONS_FILE}")
        print(f"  Total lessons: {len(lessons)}")
    elif dry_run and new_lessons:
        print(f"\n  [dry-run] Would add {len(new_lessons)} lessons")

    return new_lessons


def get_latest_report() -> Optional[str]:
    """Get path to the most recent eval report."""
    if not REPORTS_DIR.exists():
        return None
    reports = sorted(REPORTS_DIR.glob("eval-*.json"), reverse=True)
    if not reports:
        return None
    return str(reports[0])


async def main():
    parser = argparse.ArgumentParser(description="Auto-extract lessons from eval reports")
    parser.add_argument("report", nargs="?", help="Path to eval report JSON")
    parser.add_argument("--latest", action="store_true", help="Use latest report")
    parser.add_argument("--model", default="mimo-v2.5", help="LLM model for analysis")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    if args.latest:
        report_path = get_latest_report()
        if not report_path:
            print("No reports found.")
            return
    elif args.report:
        report_path = args.report
    else:
        parser.print_help()
        return

    print(f"  Report: {report_path}")
    new_lessons = await extract_lessons_from_report(
        report_path, model=args.model, dry_run=args.dry_run
    )
    print(f"  New lessons: {len(new_lessons)}")


if __name__ == "__main__":
    asyncio.run(main())
