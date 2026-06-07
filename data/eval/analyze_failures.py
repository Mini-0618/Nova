"""
Codex-Local Failure Analyzer
Reads an eval report JSON and categorizes failures.

Usage:
    python data/eval/analyze_failures.py data/eval/reports/eval-20260607-1200.json
    python data/eval/analyze_failures.py --latest
"""

import json
import sys
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any

EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR = EVAL_DIR / "reports"


def classify_failure(result: Dict[str, Any]) -> str:
    """Classify a failure into a category based on error and details."""
    error = (result.get("error") or "").lower()
    details = (result.get("details") or "").lower()
    combined = error + " " + details

    if "timeout" in combined or "timed out" in combined:
        return "timeout"

    if "importerror" in combined or "modulenotfounderror" in combined:
        return "import_error"

    if "attributeerror" in combined and "run" in combined:
        return "api_misuse"

    if "syntaxerror" in combined:
        return "syntax_error"

    if "assertionerror" in combined or "assert" in combined:
        return "wrong_fix"

    if "filenotfounderror" in combined or "no such file" in combined:
        return "file_not_found"

    if "permissionerror" in combined:
        return "permission_error"

    if "tool" in combined and ("call" in combined or "miss" in combined):
        return "tool_call_miss"

    if "401" in combined or "403" in combined or "unauthorized" in combined:
        return "auth_error"

    if "429" in combined or "rate limit" in combined:
        return "rate_limit"

    if "500" in combined or "502" in combined or "503" in combined:
        return "api_error"

    if "file not found" in combined or "not found" in combined:
        return "file_not_found"

    if "expected" in combined and "got" in combined:
        return "wrong_output"

    return "other"


def analyze_report(report_path: str) -> Dict[str, Any]:
    """Analyze an eval report and produce failure breakdown."""
    with open(report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)

    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed")]

    # Classify failures
    failure_types = Counter()
    failure_details = defaultdict(list)

    for f in failures:
        ftype = classify_failure(f)
        failure_types[ftype] += 1
        failure_details[ftype].append({
            "task_id": f["task_id"],
            "title": f["title"],
            "category": f["category"],
            "difficulty": f["difficulty"],
            "error": f.get("error", ""),
            "details": f.get("details", "")[:200]
        })

    # Category breakdown
    cat_failures = Counter(f["category"] for f in failures)
    diff_failures = Counter(f["difficulty"] for f in failures)

    analysis = {
        "report": report_path,
        "timestamp": report.get("timestamp", ""),
        "total_tasks": report.get("total_tasks", 0),
        "passed": report.get("passed", 0),
        "failed": len(failures),
        "pass_rate": report.get("pass_rate", 0),
        "failure_types": dict(failure_types.most_common()),
        "failures_by_category": dict(cat_failures.most_common()),
        "failures_by_difficulty": dict(diff_failures.most_common()),
        "details": dict(failure_details),
        "recommendations": generate_recommendations(failure_types, cat_failures, diff_failures)
    }

    return analysis


def generate_recommendations(failure_types: Counter, cat_failures: Counter, diff_failures: Counter) -> List[str]:
    """Generate actionable recommendations based on failure patterns."""
    recs = []

    # Top failure type
    if failure_types:
        top_type, top_count = failure_types.most_common(1)[0]
        total = sum(failure_types.values())
        pct = top_count / total * 100 if total > 0 else 0

        if top_type == "timeout":
            recs.append(f"HIGH: {pct:.0f}% of failures are timeouts. Increase max_iterations or timeout, or simplify tasks.")
        elif top_type == "tool_call_miss":
            recs.append(f"HIGH: {pct:.0f}% of failures are tool call misses. Fix prompt alignment — model is describing tools instead of calling them.")
        elif top_type == "wrong_fix":
            recs.append(f"HIGH: {pct:.0f}% of failures are wrong fixes. Agent is generating incorrect patches. Add more verification steps.")
        elif top_type == "import_error":
            recs.append(f"MEDIUM: {pct:.0f}% of failures are import errors. Agent may not understand project structure.")
        elif top_type == "file_not_found":
            recs.append(f"MEDIUM: {pct:.0f}% of failures are file-not-found. Agent may not be reading paths correctly.")
        elif top_type == "api_misuse":
            recs.append(f"HIGH: {pct:.0f}% of failures are API misuse (calling wrong methods). Agent doesn't know the codebase API.")
        else:
            recs.append(f"Top failure type: {top_type} ({pct:.0f}%)")

    # Category weakness
    if cat_failures:
        top_cat, top_count = cat_failures.most_common(1)[0]
        recs.append(f"Weakest category: {top_cat} ({top_count} failures). Focus improvement here.")

    # Difficulty distribution
    hard_failures = diff_failures.get("hard", 0)
    total_failures = sum(diff_failures.values())
    if total_failures > 0 and hard_failures / total_failures > 0.6:
        recs.append(f"Most failures ({hard_failures}/{total_failures}) are 'hard' difficulty. Consider breaking hard tasks into smaller subtasks.")

    return recs


def print_analysis(analysis: Dict[str, Any]):
    """Print human-readable analysis."""
    print("\n" + "=" * 55)
    print("  FAILURE ANALYSIS")
    print("=" * 55)
    print(f"\n  Report: {analysis['report']}")
    print(f"  Tasks: {analysis['total_tasks']} | Passed: {analysis['passed']} | Failed: {analysis['failed']}")
    print(f"  Pass Rate: {analysis['pass_rate']}%")

    print("\n  Failure Types:")
    for ftype, count in analysis["failure_types"].items():
        pct = count / analysis["failed"] * 100 if analysis["failed"] > 0 else 0
        bar = "#" * int(pct / 5)
        print(f"    {ftype:20s} {bar} {count} ({pct:.0f}%)")

    print("\n  Failures by Category:")
    for cat, count in analysis["failures_by_category"].items():
        print(f"    {cat:20s} {count}")

    print("\n  Failures by Difficulty:")
    for diff, count in analysis["failures_by_difficulty"].items():
        print(f"    {diff:20s} {count}")

    if analysis["recommendations"]:
        print("\n  Recommendations:")
        for i, rec in enumerate(analysis["recommendations"], 1):
            print(f"    {i}. {rec}")

    # Show details for top failure type
    if analysis["failure_types"]:
        top_type = list(analysis["failure_types"].keys())[0]
        details = analysis["details"].get(top_type, [])
        if details:
            print(f"\n  Details for '{top_type}' ({len(details)} tasks):")
            for d in details[:5]:
                print(f"    [{d['task_id']}] {d['title']}")
                if d["error"]:
                    print(f"      Error: {d['error'][:80]}")

    print("\n" + "=" * 55)


def main():
    parser = argparse.ArgumentParser(description="Analyze eval failures")
    parser.add_argument("report", nargs="?", help="Path to eval report JSON")
    parser.add_argument("--latest", action="store_true", help="Use latest report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.latest:
        reports = sorted(REPORTS_DIR.glob("eval-*.json"), reverse=True)
        if not reports:
            print("No reports found in", REPORTS_DIR)
            return
        report_path = str(reports[0])
    elif args.report:
        report_path = args.report
    else:
        parser.print_help()
        return

    analysis = analyze_report(report_path)

    if args.json:
        print(json.dumps(analysis, indent=2, ensure_ascii=False))
    else:
        print_analysis(analysis)


if __name__ == "__main__":
    main()
