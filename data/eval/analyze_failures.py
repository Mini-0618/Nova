"""
Failure Analyzer
Reads an eval report JSON and categorizes failures by type.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any
from collections import Counter


FAILURE_CATEGORIES = {
    "tool_call_miss": [
        "no tools used", "described instead of doing", "no tool calls",
        "tool_call_miss", "no tools called", "did not use any tools",
        "not using tools", "failed to call", "no tools were used",
        "tool_calls must be followed", "assistant message with tool_calls",
    ],
    "wrong_fix": [
        "assertion", "expected", "got:", "wrong", "assert", "incorrect",
        "did not fix", "wrong fix", "wrong output", "fix failed",
        "still failing", "not fixed", "fix didn't work",
    ],
    "timeout": [
        "timeout", "timed out", "max_iterations", "time limit",
        "exceeded time", "took too long", "timedout",
    ],
    "import_error": [
        "importerror", "modulenotfounderror", "no module named",
        "cannot import", "import error", "module not found",
        "unresolved import",
    ],
    "other": [],
}


def categorize_failure(error: str, details: str) -> str:
    """Categorize a failure based on error message and details."""
    text = (error + " " + details).lower()

    for category, keywords in FAILURE_CATEGORIES.items():
        if category == "other":
            continue
        for keyword in keywords:
            if keyword in text:
                return category

    return "other"


def analyze_report(report_path: str) -> Dict[str, Any]:
    """Analyze an eval report and categorize failures."""
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed", True)]

    # Categorize
    categories = Counter()
    categorized_failures = []

    for failure in failures:
        error = failure.get("error", "") or ""
        details = failure.get("details", "") or ""
        category = categorize_failure(error, details)
        categories[category] += 1

        categorized_failures.append({
            "task_id": failure.get("task_id", "unknown"),
            "title": failure.get("title", "unknown"),
            "category": category,
            "error": error[:200],
            "details": details[:200],
            "difficulty": failure.get("difficulty", "unknown"),
        })

    # Summary
    analysis = {
        "report_path": report_path,
        "total_tasks": len(results),
        "total_failures": len(failures),
        "pass_rate": report.get("pass_rate", 0),
        "failure_categories": dict(categories),
        "categorized_failures": categorized_failures,
        "top_failure_category": categories.most_common(1)[0] if categories else ("none", 0),
        "recommendations": [],
    }

    # Generate recommendations
    if categories.get("file_not_found", 0) > 0:
        analysis["recommendations"].append(
            "Files not created: LLM may be describing actions instead of executing them. "
            "Ensure tool-use reminder is active."
        )
    if categories.get("wrong_fix", 0) > 0:
        analysis["recommendations"].append(
            "Wrong fixes applied: LLM may not be reading error messages carefully. "
            "Inject 'run test first, then fix' instruction."
        )
    if categories.get("timeout", 0) > 0:
        analysis["recommendations"].append(
            "Timeouts: Tasks may be too complex for current token budget. "
            "Consider increasing max_iterations or using smart trimming."
        )
    if categories.get("import_error", 0) > 0:
        analysis["recommendations"].append(
            "Import errors: Check file names vs import statements. "
            "Ensure __init__.py files exist."
        )

    return analysis


def print_analysis(analysis: Dict[str, Any]):
    """Print analysis in human-readable format."""
    print(f"\n{'='*50}")
    print(f"  FAILURE ANALYSIS REPORT")
    print(f"{'='*50}")
    print(f"  Total tasks: {analysis['total_tasks']}")
    print(f"  Failures: {analysis['total_failures']}")
    print(f"  Pass rate: {analysis['pass_rate']}%")

    print(f"\n  Failure Categories:")
    for cat, count in sorted(analysis["failure_categories"].items(),
                             key=lambda x: x[1], reverse=True):
        bar = "#" * count
        print(f"    {cat:20s} {bar} ({count})")

    if analysis["categorized_failures"]:
        print(f"\n  Failure Details:")
        for f in analysis["categorized_failures"]:
            print(f"    [{f['task_id']}] {f['title']}")
            print(f"      Category: {f['category']}")
            print(f"      Error: {f['error'][:80]}")

    if analysis["recommendations"]:
        print(f"\n  Recommendations:")
        for i, rec in enumerate(analysis["recommendations"], 1):
            print(f"    {i}. {rec}")

    print(f"\n{'='*50}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: analyze latest report
        reports_dir = Path(__file__).parent / "reports"
        reports = sorted(reports_dir.glob("*.json"), reverse=True)
        if not reports:
            print("No reports found")
            sys.exit(1)
        report_path = str(reports[0])
    else:
        report_path = sys.argv[1]

    analysis = analyze_report(report_path)
    print_analysis(analysis)

    # Save analysis
    output_path = Path(report_path).parent / (Path(report_path).stem + "_analysis.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"\nAnalysis saved to: {output_path}")
