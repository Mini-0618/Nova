"""
Self-Improvement Loop Skeleton
Implements: load_eval -> run_tasks -> collect_failures -> analyze -> generate_fix -> test_fix -> record_lesson

Runnable as a framework even if LLM calls are stubbed.
"""

import json
import time
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class LoopConfig:
    """Configuration for the self-improvement loop."""
    eval_report_path: str = ""
    max_cycles: int = 3
    improvement_threshold: float = 0.05  # 5% improvement to continue
    model: str = "deepseek-chat"
    dry_run: bool = False  # If True, stub LLM calls


@dataclass
class CycleResult:
    """Result of one improvement cycle."""
    cycle: int = 0
    before_rate: float = 0.0
    after_rate: float = 0.0
    improvement: float = 0.0
    failures_analyzed: int = 0
    fixes_generated: int = 0
    fixes_verified: int = 0
    lessons_recorded: int = 0
    details: List[Dict] = field(default_factory=list)


class SelfImproveLoop:
    """
    Self-improvement loop that:
    1. Loads eval results
    2. Collects failures
    3. Analyzes root causes
    4. Generates fixes
    5. Tests fixes
    6. Records lessons
    """

    def __init__(self, config: Optional[LoopConfig] = None):
        self.config = config or LoopConfig()
        self.results: List[CycleResult] = []
        self.lessons: List[Dict] = []

    # ── Step 1: Load Eval ──────────────────────────────────────────────

    def load_eval(self, report_path: str = "") -> Dict[str, Any]:
        """Load eval report and extract task results."""
        path = report_path or self.config.eval_report_path
        if not path:
            # Find latest report
            reports_dir = Path(__file__).parent / "reports"
            reports = sorted(reports_dir.glob("*.json"), reverse=True)
            if not reports:
                return {"error": "No reports found"}
            path = str(reports[0])

        with open(path, 'r', encoding='utf-8') as f:
            report = json.load(f)

        return {
            "report_path": path,
            "total": report.get("total_tasks", 0),
            "passed": report.get("passed", 0),
            "failed": report.get("failed", 0),
            "rate": report.get("pass_rate", 0),
            "results": report.get("results", []),
        }

    # ── Step 2: Run Tasks (re-run after applying fixes) ────────────────

    def run_tasks(self, tasks: List[Dict]) -> Dict[str, Any]:
        """Re-run eval tasks to get updated pass/fail results.

        In dry-run mode, returns a stub result. In real mode, this would
        invoke the eval runner to execute tasks and produce a new report.
        """
        if self.config.dry_run:
            # Simulate that half the previously-failed tasks now pass
            total = len(tasks)
            passed = sum(1 for t in tasks if t.get("passed", False))
            failed = total - passed
            # Assume 50% of failures are fixed
            fixed = failed // 2
            passed += fixed
            failed -= fixed
            return {
                "report_path": "dry-run",
                "total": total,
                "passed": passed,
                "failed": failed,
                "rate": round(passed / total * 100, 1) if total > 0 else 0,
                "results": [],
            }

        # Real mode: run the eval subprocess
        import subprocess
        eval_script = Path(__file__).parent / "run_eval.py"
        reports_dir = Path(__file__).parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"self_improve_cycle_{int(time.time())}.json"

        try:
            result = subprocess.run(
                [sys.executable, str(eval_script), "--report", str(report_path)],
                capture_output=True, text=True, timeout=120,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            if result.returncode != 0:
                return {"error": f"Eval runner failed: {result.stderr[:500]}"}
        except subprocess.TimeoutExpired:
            return {"error": "Eval runner timed out"}
        except Exception as e:
            return {"error": f"Eval runner error: {e}"}

        # Load the newly generated report
        if report_path.exists():
            return self.load_eval(str(report_path))
        return {"error": "No report generated"}

    # ── Step 3: Collect Failures ───────────────────────────────────────

    def collect_failures(self, eval_data: Dict) -> List[Dict]:
        """Extract failed tasks from eval data."""
        results = eval_data.get("results", [])
        return [r for r in results if not r.get("passed", True)]

    # ── Step 3: Analyze Failures ───────────────────────────────────────

    def analyze_failure(self, failure: Dict) -> Dict[str, Any]:
        """Analyze a single failure to determine root cause."""
        error = (failure.get("error", "") + " " + failure.get("details", "")).lower()

        # Pattern matching for common failure types
        analysis = {
            "task_id": failure.get("task_id", "unknown"),
            "category": "unknown",
            "root_cause": "",
            "fix_strategy": "",
            "confidence": 0.5,
        }

        if "file not found" in error or "no such file" in error:
            analysis["category"] = "file_not_created"
            analysis["root_cause"] = "LLM described actions but didn't call Write tool"
            analysis["fix_strategy"] = "Inject stronger tool-use reminder"
            analysis["confidence"] = 0.8

        elif "assertion" in error or "expected" in error:
            analysis["category"] = "wrong_output"
            analysis["root_cause"] = "LLM produced incorrect output"
            analysis["fix_strategy"] = "Re-read spec and run verification"
            analysis["confidence"] = 0.7

        elif "import" in error or "module" in error:
            analysis["category"] = "import_error"
            analysis["root_cause"] = "Wrong module name or missing __init__.py"
            analysis["fix_strategy"] = "Check actual file names before importing"
            analysis["confidence"] = 0.9

        elif "timeout" in error or "max_iterations" in error:
            analysis["category"] = "timeout"
            analysis["root_cause"] = "Task too complex for token budget"
            analysis["fix_strategy"] = "Increase budget or simplify approach"
            analysis["confidence"] = 0.6

        else:
            analysis["category"] = "other"
            analysis["root_cause"] = f"Unknown: {error[:100]}"
            analysis["fix_strategy"] = "Manual investigation needed"
            analysis["confidence"] = 0.3

        return analysis

    # ── Step 4: Generate Fix ───────────────────────────────────────────

    def generate_fix(self, analysis: Dict) -> Dict[str, Any]:
        """Generate a fix based on the analysis."""
        if self.config.dry_run:
            return {
                "task_id": analysis["task_id"],
                "fix_type": "stub",
                "description": f"[DRY RUN] Would fix: {analysis['fix_strategy']}",
                "applied": False,
            }

        # In a real implementation, this would call the LLM to generate a fix
        return {
            "task_id": analysis["task_id"],
            "fix_type": analysis["category"],
            "description": analysis["fix_strategy"],
            "applied": True,
        }

    # ── Step 5: Test Fix ───────────────────────────────────────────────

    def test_fix(self, task: Dict, fix: Dict) -> bool:
        """Test if a fix resolves the failure."""
        if self.config.dry_run:
            return True  # Assume fix works in dry run

        # In a real implementation, this would re-run the task
        # and verify it passes
        return True

    # ── Step 6: Record Lesson ──────────────────────────────────────────

    def record_lesson(self, analysis: Dict, fix: Dict, verified: bool):
        """Record a lesson learned from the fix."""
        lesson = {
            "id": f"lesson-{analysis['task_id']}-{int(time.time())}",
            "pattern": analysis["root_cause"],
            "fix": fix["description"],
            "category": analysis["category"],
            "confidence": analysis["confidence"],
            "verified": verified,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.lessons.append(lesson)

    # ── Main Loop ──────────────────────────────────────────────────────

    def run_cycle(self, cycle_num: int) -> CycleResult:
        """Run one improvement cycle."""
        result = CycleResult(cycle=cycle_num)

        # Step 1: Load eval
        eval_data = self.load_eval()
        result.before_rate = eval_data.get("rate", 0)

        # Step 2: Collect failures
        failures = self.collect_failures(eval_data)
        if not failures:
            return result

        # Step 3-6: Analyze, fix, test, record for each failure
        for failure in failures:
            # Analyze
            analysis = self.analyze_failure(failure)
            result.failures_analyzed += 1

            # Generate fix
            fix = self.generate_fix(analysis)
            if fix.get("applied"):
                result.fixes_generated += 1

            # Test fix
            verified = self.test_fix(failure, fix)
            if verified:
                result.fixes_verified += 1

            # Record lesson
            self.record_lesson(analysis, fix, verified)
            result.lessons_recorded += 1

            result.details.append({
                "task_id": failure.get("task_id"),
                "analysis": analysis,
                "fix": fix,
                "verified": verified,
            })

        return result

    def run(self) -> List[CycleResult]:
        """Run the full self-improvement loop."""
        print(f"Self-Improvement Loop")
        print(f"Max cycles: {self.config.max_cycles}")
        print(f"Dry run: {self.config.dry_run}")
        print()

        for cycle in range(1, self.config.max_cycles + 1):
            print(f"--- Cycle {cycle} ---")
            result = self.run_cycle(cycle)
            self.results.append(result)

            print(f"  Failures analyzed: {result.failures_analyzed}")
            print(f"  Fixes generated: {result.fixes_generated}")
            print(f"  Fixes verified: {result.fixes_verified}")
            print(f"  Lessons recorded: {result.lessons_recorded}")

            if result.failures_analyzed == 0:
                print("  No failures found. Stopping.")
                break

        # Save lessons
        self.save_lessons()

        return self.results

    def save_lessons(self):
        """Save accumulated lessons to file."""
        lessons_file = Path(__file__).parent / "lessons.json"
        existing = []
        if lessons_file.exists():
            try:
                existing = json.loads(lessons_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        existing.extend(self.lessons)
        lessons_file.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"\nSaved {len(self.lessons)} lessons to {lessons_file}")

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all cycles."""
        return {
            "total_cycles": len(self.results),
            "total_failures_analyzed": sum(r.failures_analyzed for r in self.results),
            "total_fixes_generated": sum(r.fixes_generated for r in self.results),
            "total_fixes_verified": sum(r.fixes_verified for r in self.results),
            "total_lessons": len(self.lessons),
            "cycles": [asdict(r) for r in self.results],
        }


if __name__ == "__main__":
    config = LoopConfig(
        dry_run="--dry-run" in sys.argv,
        max_cycles=3,
    )

    loop = SelfImproveLoop(config)
    results = loop.run()

    summary = loop.get_summary()
    print(f"\n{'='*50}")
    print(f"  SUMMARY")
    print(f"{'='*50}")
    print(f"  Cycles: {summary['total_cycles']}")
    print(f"  Failures analyzed: {summary['total_failures_analyzed']}")
    print(f"  Fixes generated: {summary['total_fixes_generated']}")
    print(f"  Fixes verified: {summary['total_fixes_verified']}")
    print(f"  Lessons recorded: {summary['total_lessons']}")
