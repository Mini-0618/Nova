"""
Codex-Local Plan Runner
Reads a plan file (JSON), executes tasks one by one using CodexLoop.
Supports: pause/resume, error handling, progress tracking, auto-retry.

Usage:
    python -m codex_local.runtime.plan_runner run plan.json
    python -m codex_local.runtime.plan_runner run plan.json --resume
    python -m codex_local.runtime.plan_runner status
"""

import os
import json
import time
import asyncio
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import datetime


DATA_DIR = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
PLANS_DIR = DATA_DIR / "plans"
PROGRESS_DIR = DATA_DIR / "progress"
REPORTS_DIR = DATA_DIR / "reports"

for d in [PLANS_DIR, PROGRESS_DIR, REPORTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class PlanTask:
    id: str
    title: str
    description: str
    type: str  # code, test, refactor, document, analyze, fix
    target: Optional[str] = None  # file/directory target
    status: str = "pending"  # pending, running, completed, failed, skipped
    retry_count: int = 0
    max_retries: int = 2
    error: Optional[str] = None
    result: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_s: float = 0.0
    depends_on: List[str] = field(default_factory=list)  # task IDs this task depends on


@dataclass
class Plan:
    id: str
    name: str
    description: str
    tasks: List[PlanTask]
    status: str = "pending"  # pending, running, completed, paused, failed
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_task_index: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    skipped_tasks: int = 0


class PlanRunner:
    """Executes a plan by running tasks through CodexLoop."""

    def __init__(self, workspace: str = "D:/codex-local"):
        self.workspace = Path(workspace)
        self.progress_path: Optional[Path] = None

    def load_plan(self, plan_path: str) -> Plan:
        """Load a plan from JSON file."""
        with open(plan_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        tasks = []
        for t in data.get('tasks', []):
            tasks.append(PlanTask(**t))

        plan = Plan(
            id=data.get('id', f"plan-{int(time.time())}"),
            name=data.get('name', 'Unnamed Plan'),
            description=data.get('description', ''),
            tasks=tasks,
            created_at=data.get('created_at', datetime.now().isoformat()),
            total_tasks=len(tasks),
        )
        return plan

    def save_progress(self, plan: Plan) -> None:
        """Save plan progress to file."""
        self.progress_path = PROGRESS_DIR / f"{plan.id}.json"
        data = {
            'id': plan.id,
            'name': plan.name,
            'description': plan.description,
            'status': plan.status,
            'created_at': plan.created_at,
            'started_at': plan.started_at,
            'finished_at': plan.finished_at,
            'current_task_index': plan.current_task_index,
            'total_tasks': plan.total_tasks,
            'completed_tasks': plan.completed_tasks,
            'failed_tasks': plan.failed_tasks,
            'skipped_tasks': plan.skipped_tasks,
            'tasks': [asdict(t) for t in plan.tasks],
        }
        with open(self.progress_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load_progress(self, plan_id: str) -> Optional[Plan]:
        """Load saved progress."""
        path = PROGRESS_DIR / f"{plan_id}.json"
        if not path.exists():
            return None
        return self.load_plan(str(path))

    def get_task_prompt(self, task: PlanTask, plan: Plan) -> str:
        """Generate a prompt for CodexLoop from a plan task."""
        context = f"Plan: {plan.name} ({plan.completed_tasks}/{plan.total_tasks} done)\n"
        context += f"Current task: {task.title}\n"
        context += f"Type: {task.type}\n"

        if task.target:
            context += f"Target: {task.target}\n"

        if task.error and task.retry_count > 0:
            context += f"\nPrevious attempt failed: {task.error}\n"
            context += "Please try a different approach.\n"

        prompt = f"""{context}

{task.description}

Requirements:
1. Complete this task fully
2. Test your changes if applicable
3. Report what you did and any issues found
4. If the task cannot be completed, explain why
"""
        return prompt

    async def execute_task(self, task: PlanTask, plan: Plan, model: str = "deepseek-chat") -> PlanTask:
        """Execute a single task using CodexLoop."""
        from runtime.loop import CodexLoop, LoopConfig

        task.status = "running"
        task.started_at = datetime.now().isoformat()
        start_time = time.time()

        try:
            prompt = self.get_task_prompt(task, plan)

            config = LoopConfig(
                model=model,
                max_iterations=20,
                workspace=str(self.workspace),
            )

            loop = CodexLoop(config)
            result = await loop.run_task(prompt)

            task.result = result if isinstance(result, str) else str(result)
            task.status = "completed"

        except Exception as e:
            task.error = f"{type(e).__name__}: {str(e)}"
            task.status = "failed"
            task.result = traceback.format_exc()

        finally:
            task.finished_at = datetime.now().isoformat()
            task.duration_s = round(time.time() - start_time, 2)

        return task

    @staticmethod
    def topological_sort(tasks: List[PlanTask]) -> List[PlanTask]:
        """Sort tasks by dependency order using Kahn's algorithm.

        Returns tasks in topological order. Raises ValueError on circular deps.
        """
        task_map = {t.id: t for t in tasks}
        # Build adjacency: for each task, which tasks depend on it
        in_degree = {t.id: 0 for t in tasks}
        dependents = {t.id: [] for t in tasks}  # task_id -> list of tasks that depend on it

        for t in tasks:
            for dep_id in t.depends_on:
                if dep_id in task_map:
                    dependents[dep_id].append(t.id)
                    in_degree[t.id] += 1

        # Start with tasks that have no dependencies
        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            tid = queue.pop(0)
            result.append(task_map[tid])
            for dependent_id in dependents[tid]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        if len(result) != len(tasks):
            missing = [t.id for t in tasks if t.id not in {r.id for r in result}]
            raise ValueError(f"Circular dependency detected involving tasks: {missing}")

        return result

    def _check_dependencies_met(self, task: PlanTask, plan: Plan) -> bool:
        """Check if all dependencies of a task are completed."""
        task_map = {t.id: t for t in plan.tasks}
        for dep_id in task.depends_on:
            dep_task = task_map.get(dep_id)
            if dep_task is None:
                return False  # dependency not found
            if dep_task.status != "completed":
                return False
        return True

    def _load_or_resume_plan(self, plan_path: str, resume: bool) -> Plan:
        """Load a fresh plan or resume from saved progress."""
        if resume:
            plan_data = self.load_plan(plan_path)
            saved = self.load_progress(plan_data.id)
            if saved:
                print(f"Resuming plan: {saved.name} from task {saved.current_task_index + 1}/{saved.total_tasks}")
                return saved
            print(f"No saved progress found. Starting fresh: {plan_data.name}")
            return plan_data
        return self.load_plan(plan_path)

    def _print_task_header(self, task: PlanTask, is_deferred: bool = False) -> None:
        suffix = " (deferred retry)" if is_deferred else ""
        print(f"[{task.id}] {task.title}{suffix}")
        print(f"  Type: {task.type}")
        if task.target:
            print(f"  Target: {task.target}")
        if task.depends_on:
            print(f"  Depends on: {task.depends_on}")

    async def _execute_task_with_retry(self, task: PlanTask, plan: Plan, model: str) -> None:
        """Execute a task with retry logic, updating plan counters."""
        while task.retry_count <= task.max_retries:
            task = await self.execute_task(task, plan, model)
            if task.status == "completed":
                plan.completed_tasks += 1
                print(f"  DONE ({task.duration_s}s)")
                return
            task.retry_count += 1
            if task.retry_count <= task.max_retries:
                print(f"  FAILED (retry {task.retry_count}/{task.max_retries})")
                print(f"  Error: {task.error}")
            else:
                plan.failed_tasks += 1
                print(f"  FAILED (max retries reached)")
                print(f"  Error: {task.error}")

    async def _run_main_tasks(self, sorted_tasks: List[PlanTask], plan: Plan, model: str) -> List[PlanTask]:
        """Execute main task list, returning deferred tasks."""
        deferred = []
        for task in sorted_tasks:
            orig_idx = next(i for i, t in enumerate(plan.tasks) if t.id == task.id)
            plan.current_task_index = orig_idx
            self._print_task_header(task)
            if task.status == "completed":
                plan.completed_tasks += 1
                print(f"  SKIP (already completed)")
                continue
            if not self._check_dependencies_met(task, plan):
                task.status = "skipped"
                deferred.append(task)
                plan.skipped_tasks += 1
                self.save_progress(plan)
                continue
            await self._execute_task_with_retry(task, plan, model)
            self.save_progress(plan)
            if plan.failed_tasks > 0:
                plan.status = "partial"
        return deferred

    async def _run_deferred_tasks(self, deferred: List[PlanTask], plan: Plan, model: str) -> None:
        """Execute deferred tasks whose dependencies are now met."""
        print(f"\n{'='*60}\nRunning {len(deferred)} deferred tasks...\n{'='*60}\n")
        for task in deferred:
            if not self._check_dependencies_met(task, plan):
                print(f"[{task.id}] {task.title} — STILL BLOCKED, skipping")
                continue
            task.status = "pending"
            task.retry_count = 0
            plan.skipped_tasks -= 1
            self._print_task_header(task, is_deferred=True)
            await self._execute_task_with_retry(task, plan, model)
            self.save_progress(plan)

    def _finalize_plan(self, plan: Plan) -> None:
        """Set final plan status and generate report."""
        if plan.failed_tasks == 0:
            plan.status = "completed"
        elif plan.completed_tasks > 0:
            plan.status = "partial"
        else:
            plan.status = "failed"
        plan.finished_at = datetime.now().isoformat()
        self.save_progress(plan)
        self.generate_report(plan)

    def _sort_tasks(self, plan: Plan) -> Optional[List[PlanTask]]:
        """Topological sort of plan tasks, returning None on dependency error."""
        try:
            return self.topological_sort(plan.tasks)
        except ValueError as e:
            print(f"Dependency error: {e}")
            plan.status = "failed"
            plan.finished_at = datetime.now().isoformat()
            self.save_progress(plan)
            return None

    async def run_plan(self, plan_path: str, resume: bool = False, model: str = "deepseek-chat") -> Plan:
        """Execute a full plan with dependency-aware ordering."""
        plan = self._load_or_resume_plan(plan_path, resume)
        plan.status = "running"
        plan.started_at = plan.started_at or datetime.now().isoformat()
        self.save_progress(plan)
        sorted_tasks = self._sort_tasks(plan)
        if sorted_tasks is None:
            return plan
        print(f"\n{'='*60}\nPlan: {plan.name}\nTasks: {plan.total_tasks} (dependency-sorted)\n{'='*60}\n")
        deferred = await self._run_main_tasks(sorted_tasks, plan, model)
        if deferred:
            await self._run_deferred_tasks(deferred, plan, model)
        self._finalize_plan(plan)
        return plan

    def _report_task_table(self, plan: Plan) -> list:
        """Build the task status table rows for the report."""
        icons = {"completed": "✅", "failed": "❌", "skipped": "⏭️",
                 "pending": "⏳", "running": "\U0001f504"}
        lines = ["## Tasks", "", "| # | Task | Type | Status | Duration |",
                 "|---|------|------|--------|----------|"]
        for i, task in enumerate(plan.tasks):
            icon = icons.get(task.status, "❓")
            lines.append(f"| {i+1} | {task.title} | {task.type} | {icon} {task.status} | {task.duration_s}s |")
        lines.append("")
        return lines

    def _report_failed_detail(self, plan: Plan) -> list:
        """Build failed task detail section."""
        failed = [t for t in plan.tasks if t.status == "failed"]
        if not failed:
            return []
        lines = ["## Failed Tasks", ""]
        for task in failed:
            lines.extend([f"### {task.title}", f"- Error: {task.error}", f"- Retries: {task.retry_count}"])
            if task.result:
                lines.extend(["```", task.result[:500], "```"])
            lines.append("")
        return lines

    def generate_report(self, plan: Plan) -> str:
        """Generate a markdown report of the plan execution."""
        report_path = REPORTS_DIR / f"{plan.id}.md"
        lines = [f"# Plan Report: {plan.name}", "",
                 f"- **Plan ID**: {plan.id}", f"- **Status**: {plan.status}",
                 f"- **Started**: {plan.started_at}", f"- **Finished**: {plan.finished_at}",
                 f"- **Total**: {plan.total_tasks} tasks", f"- **Completed**: {plan.completed_tasks}",
                 f"- **Failed**: {plan.failed_tasks}", f"- **Skipped**: {plan.skipped_tasks}", ""]
        lines.extend(self._report_task_table(plan))
        lines.extend(self._report_failed_detail(plan))
        completed = [t for t in plan.tasks if t.status == "completed"]
        if completed:
            lines.extend(["## Completed Tasks", ""])
            for task in completed:
                lines.append(f"- ✅ {task.title} ({task.duration_s}s)")
            lines.append("")
        report = "\n".join(lines)
        report_path.write_text(report, encoding='utf-8')
        print(f"\nReport saved: {report_path}")
        return str(report_path)

    def _build_plan_summary(self, completed_plan: Plan) -> str:
        """Build a text summary of completed plan results."""
        completed = [t for t in completed_plan.tasks if t.status == "completed"]
        failed = [t for t in completed_plan.tasks if t.status == "failed"]
        lines = [f"Previous plan: {completed_plan.name}",
                 f"Completed: {len(completed)}/{completed_plan.total_tasks}",
                 f"Failed: {len(failed)}", ""]
        if completed:
            lines.append("What was done:")
            for t in completed:
                lines.append(f"- {t.title}: {t.result[:100] if t.result else 'done'}")
        if failed:
            lines.append("\nWhat failed:")
            for t in failed:
                lines.append(f"- {t.title}: {t.error}")
        return "\n".join(lines)

    def _parse_plan_response(self, response: str) -> Optional[Plan]:
        """Extract and save a JSON plan from LLM response text."""
        decoder = json.JSONDecoder()
        for start_idx in range(len(response)):
            if response[start_idx] == '{':
                try:
                    plan_data, _ = decoder.raw_decode(response, start_idx)
                    plan_data['id'] = f"plan-{int(time.time())}"
                    plan_data['created_at'] = datetime.now().isoformat()
                    plan_path = PLANS_DIR / f"{plan_data['id']}.json"
                    with open(plan_path, 'w', encoding='utf-8') as f:
                        json.dump(plan_data, f, indent=2, ensure_ascii=False)
                    return self.load_plan(str(plan_path))
                except json.JSONDecodeError:
                    continue
        return None

    _PLAN_PROMPT_TEMPLATE = """Based on the previous work, generate the NEXT plan.

{summary}

Requirements:
1. If there were failures, create tasks to fix them
2. If everything succeeded, create tasks for the next logical step
3. Each task should be specific and actionable
4. Limit to 3-5 tasks
5. Output ONLY a JSON plan object, no other text

Output format:
{{"name": "Next: <plan name>", "description": "<what this plan achieves>",
  "tasks": [{{"id": "task-001", "title": "<title>", "description": "<desc>",
  "type": "code|test|fix|analyze|document|refactor", "target": "<file>"}}]}}"""

    async def generate_next_plan(self, completed_plan: Plan, model: str = "deepseek-chat") -> Optional[Plan]:
        """Generate the next plan based on completed plan results."""
        from runtime.loop import CodexLoop, LoopConfig
        summary = self._build_plan_summary(completed_plan)
        prompt = self._PLAN_PROMPT_TEMPLATE.format(summary=summary)
        try:
            config = LoopConfig(model=model, max_iterations=5, workspace=str(self.workspace))
            loop = CodexLoop(config)
            result = await loop.run_task(prompt)
            return self._parse_plan_response(result if isinstance(result, str) else str(result))
        except Exception as e:
            print(f"Failed to generate next plan: {e}")
            return None

    async def run_loop(self, initial_plan_path: str, max_cycles: int = 5, model: str = "deepseek-chat") -> List[Plan]:
        """Run the auto-loop: execute → summarize → plan next → execute → ...

        This is the autonomous cycle that keeps running while you're away.
        """
        plans = []
        current_plan_path = initial_plan_path

        print(f"\n{'#'*60}")
        print(f"AUTO-LOOP: Starting (max {max_cycles} cycles)")
        print(f"{'#'*60}\n")

        for cycle in range(max_cycles):
            print(f"\n{'='*60}")
            print(f"CYCLE {cycle + 1}/{max_cycles}")
            print(f"{'='*60}\n")

            # Execute current plan
            plan = await self.run_plan(current_plan_path, resume=(cycle > 0), model=model)
            plans.append(plan)

            print(f"\nCycle {cycle + 1} result: {plan.status}")
            print(f"  Completed: {plan.completed_tasks}/{plan.total_tasks}")

            # Check if we should continue
            if plan.status == "failed":
                print(f"\nPlan failed. Stopping loop.")
                break

            if plan.completed_tasks == 0:
                print(f"\nNo progress made. Stopping loop.")
                break

            # Generate next plan
            print(f"\nGenerating next plan...")
            next_plan = await self.generate_next_plan(plan, model)

            if not next_plan:
                print(f"Could not generate next plan. Stopping loop.")
                break

            print(f"Next plan: {next_plan.name} ({next_plan.total_tasks} tasks)")
            current_plan_path = str(PLANS_DIR / f"{next_plan.id}.json")

        # Generate final summary
        self.generate_loop_summary(plans)

        return plans

    def generate_loop_summary(self, plans: List[Plan]) -> None:
        """Generate a summary of all plans in the loop."""
        summary_path = REPORTS_DIR / f"loop-summary-{int(time.time())}.md"

        lines = []
        lines.append("# Auto-Loop Summary")
        lines.append("")
        lines.append(f"- **Cycles**: {len(plans)}")
        lines.append(f"- **Total tasks**: {sum(p.total_tasks for p in plans)}")
        lines.append(f"- **Total completed**: {sum(p.completed_tasks for p in plans)}")
        lines.append(f"- **Total failed**: {sum(p.failed_tasks for p in plans)}")
        lines.append("")
        lines.append("## Plans")
        lines.append("")

        for i, plan in enumerate(plans):
            status_icon = {"completed": "✅", "partial": "⚠️", "failed": "❌"}.get(plan.status, "❓")
            lines.append(f"### Cycle {i+1}: {plan.name}")
            lines.append(f"- Status: {status_icon} {plan.status}")
            lines.append(f"- Tasks: {plan.completed_tasks}/{plan.total_tasks} completed")
            lines.append(f"- Duration: {plan.finished_at}")
            lines.append("")

        summary = "\n".join(lines)
        summary_path.write_text(summary, encoding='utf-8')
        print(f"\nLoop summary saved: {summary_path}")

    def show_status(self) -> None:
        """Show status of all plans."""
        plans = list(PROGRESS_DIR.glob("*.json"))
        if not plans:
            print("No plans found.")
            return

        print(f"\n{'='*60}")
        print("Plan Status")
        print(f"{'='*60}\n")

        for plan_path in sorted(plans):
            with open(plan_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            status_icon = {
                "completed": "✅",
                "partial": "⚠️",
                "failed": "❌",
                "running": "🔄",
                "paused": "⏸️",
                "pending": "⏳",
            }.get(data.get('status', 'pending'), "❓")

            print(f"{status_icon} {data.get('name', 'Unknown')}")
            print(f"   Status: {data.get('status', '?')}")
            print(f"   Tasks: {data.get('completed_tasks', 0)}/{data.get('total_tasks', 0)} completed")
            if data.get('failed_tasks', 0) > 0:
                print(f"   Failed: {data.get('failed_tasks', 0)}")
            print()


_EXAMPLE_TASKS = [
    {"id": "task-001", "title": "Analyze project structure",
     "description": "List all Python files, check imports, identify main modules.", "type": "analyze", "target": "."},
    {"id": "task-002", "title": "Find and fix syntax errors",
     "description": "Run py_compile on all .py files, fix any syntax errors found.", "type": "fix", "target": "."},
    {"id": "task-003", "title": "Add type hints",
     "description": "Add type hints to function signatures in the main modules.", "type": "code", "target": "runtime/"},
    {"id": "task-004", "title": "Write tests",
     "description": "Create pytest tests for the main functions.", "type": "test", "target": "tests/"},
    {"id": "task-005", "title": "Update documentation",
     "description": "Update README.md with current API and usage examples.", "type": "document", "target": "README.md"},
]


def create_example_plan() -> str:
    """Create an example plan file."""
    plan = {
        "id": "example-plan-001",
        "name": "Example: Refactor a Python Project",
        "description": "An example plan showing how to use the plan runner.",
        "created_at": datetime.now().isoformat(),
        "tasks": _EXAMPLE_TASKS,
    }
    path = PLANS_DIR / "example-plan.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print(f"Example plan created: {path}")
    return str(path)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Codex-Local Plan Runner")
    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Execute a plan")
    run_p.add_argument("plan_path", help="Path to plan JSON file")
    run_p.add_argument("--resume", action="store_true", help="Resume from saved progress")
    run_p.add_argument("--model", default="deepseek-chat", help="LLM model to use")

    # status
    sub.add_parser("status", help="Show plan status")

    # example
    sub.add_parser("example", help="Create an example plan")

    args = parser.parse_args()

    if args.command == "run":
        runner = PlanRunner()
        plan = asyncio.run(runner.run_plan(args.plan_path, args.resume, args.model))
        print(f"\nPlan {plan.status}: {plan.completed_tasks}/{plan.total_tasks} tasks completed")

    elif args.command == "status":
        runner = PlanRunner()
        runner.show_status()

    elif args.command == "example":
        create_example_plan()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
