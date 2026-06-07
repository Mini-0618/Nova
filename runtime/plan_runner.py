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

    async def run_plan(self, plan_path: str, resume: bool = False, model: str = "deepseek-chat") -> Plan:
        """Execute a full plan with dependency-aware ordering."""
        # Load or resume plan
        if resume:
            plan_data = self.load_plan(plan_path)
            saved = self.load_progress(plan_data.id)
            if saved:
                plan = saved
                print(f"Resuming plan: {plan.name} from task {plan.current_task_index + 1}/{plan.total_tasks}")
            else:
                plan = plan_data
                print(f"No saved progress found. Starting fresh: {plan.name}")
        else:
            plan = self.load_plan(plan_path)

        plan.status = "running"
        plan.started_at = plan.started_at or datetime.now().isoformat()
        self.save_progress(plan)

        # Topological sort for dependency-aware execution
        try:
            sorted_tasks = self.topological_sort(plan.tasks)
        except ValueError as e:
            print(f"Dependency error: {e}")
            plan.status = "failed"
            plan.finished_at = datetime.now().isoformat()
            self.save_progress(plan)
            return plan

        # Build ordered index map
        sorted_ids = [t.id for t in sorted_tasks]
        task_index_map = {t.id: i for i, t in enumerate(sorted_tasks)}

        print(f"\n{'='*60}")
        print(f"Plan: {plan.name}")
        print(f"Tasks: {plan.total_tasks} (dependency-sorted)")
        print(f"{'='*60}\n")

        # Execute tasks in topological order
        deferred_tasks = []  # tasks skipped due to unmet deps, to retry later

        for task in sorted_tasks:
            orig_idx = next(i for i, t in enumerate(plan.tasks) if t.id == task.id)
            plan.current_task_index = orig_idx

            print(f"[{task.id}] {task.title}")
            print(f"  Type: {task.type}")
            if task.target:
                print(f"  Target: {task.target}")
            if task.depends_on:
                print(f"  Depends on: {task.depends_on}")

            # Skip if already completed
            if task.status == "completed":
                print(f"  SKIP (already completed)")
                plan.completed_tasks += 1
                continue

            # Check dependencies
            if not self._check_dependencies_met(task, plan):
                print(f"  DEFERRED (dependencies not met)")
                task.status = "skipped"
                deferred_tasks.append(task)
                plan.skipped_tasks += 1
                self.save_progress(plan)
                continue

            # Execute with retry
            while task.retry_count <= task.max_retries:
                task = await self.execute_task(task, plan, model)

                if task.status == "completed":
                    plan.completed_tasks += 1
                    print(f"  DONE ({task.duration_s}s)")
                    break
                elif task.status == "failed":
                    task.retry_count += 1
                    if task.retry_count <= task.max_retries:
                        print(f"  FAILED (retry {task.retry_count}/{task.max_retries})")
                        print(f"  Error: {task.error}")
                    else:
                        plan.failed_tasks += 1
                        print(f"  FAILED (max retries reached)")
                        print(f"  Error: {task.error}")

            # Save progress after each task
            self.save_progress(plan)

            # Update plan status
            if plan.failed_tasks > 0:
                plan.status = "partial"

        # Run deferred tasks (dependencies that became available later)
        if deferred_tasks:
            print(f"\n{'='*60}")
            print(f"Running {len(deferred_tasks)} deferred tasks...")
            print(f"{'='*60}\n")

            for task in deferred_tasks:
                if not self._check_dependencies_met(task, plan):
                    print(f"[{task.id}] {task.title} — STILL BLOCKED, skipping")
                    continue

                task.status = "pending"
                task.retry_count = 0
                plan.skipped_tasks -= 1

                print(f"[{task.id}] {task.title} (deferred retry)")

                while task.retry_count <= task.max_retries:
                    task = await self.execute_task(task, plan, model)

                    if task.status == "completed":
                        plan.completed_tasks += 1
                        print(f"  DONE ({task.duration_s}s)")
                        break
                    elif task.status == "failed":
                        task.retry_count += 1
                        if task.retry_count <= task.max_retries:
                            print(f"  FAILED (retry {task.retry_count}/{task.max_retries})")
                        else:
                            plan.failed_tasks += 1
                            print(f"  FAILED (max retries reached)")

                self.save_progress(plan)

        # Final status
        if plan.failed_tasks == 0:
            plan.status = "completed"
        elif plan.completed_tasks > 0:
            plan.status = "partial"
        else:
            plan.status = "failed"

        plan.finished_at = datetime.now().isoformat()
        self.save_progress(plan)

        # Generate report
        self.generate_report(plan)

        return plan

    def generate_report(self, plan: Plan) -> str:
        """Generate a markdown report of the plan execution."""
        report_path = REPORTS_DIR / f"{plan.id}.md"

        lines = []
        lines.append(f"# Plan Report: {plan.name}")
        lines.append("")
        lines.append(f"- **Plan ID**: {plan.id}")
        lines.append(f"- **Status**: {plan.status}")
        lines.append(f"- **Started**: {plan.started_at}")
        lines.append(f"- **Finished**: {plan.finished_at}")
        lines.append(f"- **Total**: {plan.total_tasks} tasks")
        lines.append(f"- **Completed**: {plan.completed_tasks}")
        lines.append(f"- **Failed**: {plan.failed_tasks}")
        lines.append(f"- **Skipped**: {plan.skipped_tasks}")
        lines.append("")
        lines.append("## Tasks")
        lines.append("")
        lines.append("| # | Task | Type | Status | Duration |")
        lines.append("|---|------|------|--------|----------|")

        for i, task in enumerate(plan.tasks):
            status_icon = {
                "completed": "✅",
                "failed": "❌",
                "skipped": "⏭️",
                "pending": "⏳",
                "running": "🔄",
            }.get(task.status, "❓")
            lines.append(f"| {i+1} | {task.title} | {task.type} | {status_icon} {task.status} | {task.duration_s}s |")

        lines.append("")

        # Failed tasks detail
        failed = [t for t in plan.tasks if t.status == "failed"]
        if failed:
            lines.append("## Failed Tasks")
            lines.append("")
            for task in failed:
                lines.append(f"### {task.title}")
                lines.append(f"- Error: {task.error}")
                lines.append(f"- Retries: {task.retry_count}")
                if task.result:
                    lines.append(f"```")
                    lines.append(task.result[:500])
                    lines.append(f"```")
                lines.append("")

        # Completed tasks summary
        completed = [t for t in plan.tasks if t.status == "completed"]
        if completed:
            lines.append("## Completed Tasks")
            lines.append("")
            for task in completed:
                lines.append(f"- ✅ {task.title} ({task.duration_s}s)")
            lines.append("")

        report = "\n".join(lines)
        report_path.write_text(report, encoding='utf-8')
        print(f"\nReport saved: {report_path}")
        return str(report_path)

    async def generate_next_plan(self, completed_plan: Plan, model: str = "deepseek-chat") -> Optional[Plan]:
        """Generate the next plan based on completed plan results."""
        from runtime.loop import CodexLoop, LoopConfig

        # Build summary of what was done
        completed_tasks = [t for t in completed_plan.tasks if t.status == "completed"]
        failed_tasks = [t for t in completed_plan.tasks if t.status == "failed"]

        summary = f"Previous plan: {completed_plan.name}\n"
        summary += f"Completed: {len(completed_tasks)}/{completed_plan.total_tasks}\n"
        summary += f"Failed: {len(failed_tasks)}\n\n"

        if completed_tasks:
            summary += "What was done:\n"
            for t in completed_tasks:
                summary += f"- {t.title}: {t.result[:100] if t.result else 'done'}\n"

        if failed_tasks:
            summary += "\nWhat failed:\n"
            for t in failed_tasks:
                summary += f"- {t.title}: {t.error}\n"

        prompt = f"""Based on the previous work, generate the NEXT plan.

{summary}

Requirements:
1. If there were failures, create tasks to fix them
2. If everything succeeded, create tasks for the next logical step
3. Each task should be specific and actionable
4. Limit to 3-5 tasks
5. Output ONLY a JSON plan object, no other text

Output format:
{{
  "name": "Next: <plan name>",
  "description": "<what this plan achieves>",
  "tasks": [
    {{
      "id": "task-001",
      "title": "<task title>",
      "description": "<detailed description>",
      "type": "code|test|fix|analyze|document|refactor",
      "target": "<file or directory>"
    }}
  ]
}}
"""
        try:
            config = LoopConfig(
                model=model,
                max_iterations=5,
                workspace=str(self.workspace),
            )
            loop = CodexLoop(config)
            result = await loop.run_task(prompt)

            response = result if isinstance(result, str) else str(result)
            # Extract JSON from response — use raw_decode for robustness
            plan_data = None
            decoder = json.JSONDecoder()
            for start_idx in range(len(response)):
                if response[start_idx] == '{':
                    try:
                        plan_data, _ = decoder.raw_decode(response, start_idx)
                        break
                    except json.JSONDecodeError:
                        continue
            if plan_data:
                plan_data['id'] = f"plan-{int(time.time())}"
                plan_data['created_at'] = datetime.now().isoformat()

                # Save the new plan
                plan_path = PLANS_DIR / f"{plan_data['id']}.json"
                with open(plan_path, 'w', encoding='utf-8') as f:
                    json.dump(plan_data, f, indent=2, ensure_ascii=False)

                return self.load_plan(str(plan_path))

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


def create_example_plan() -> str:
    """Create an example plan file."""
    plan = {
        "id": "example-plan-001",
        "name": "Example: Refactor a Python Project",
        "description": "An example plan showing how to use the plan runner.",
        "created_at": datetime.now().isoformat(),
        "tasks": [
            {
                "id": "task-001",
                "title": "Analyze project structure",
                "description": "List all Python files, check imports, identify main modules.",
                "type": "analyze",
                "target": ".",
            },
            {
                "id": "task-002",
                "title": "Find and fix syntax errors",
                "description": "Run py_compile on all .py files, fix any syntax errors found.",
                "type": "fix",
                "target": ".",
            },
            {
                "id": "task-003",
                "title": "Add type hints",
                "description": "Add type hints to function signatures in the main modules.",
                "type": "code",
                "target": "runtime/",
            },
            {
                "id": "task-004",
                "title": "Write tests",
                "description": "Create pytest tests for the main functions.",
                "type": "test",
                "target": "tests/",
            },
            {
                "id": "task-005",
                "title": "Update documentation",
                "description": "Update README.md with current API and usage examples.",
                "type": "document",
                "target": "README.md",
            },
        ]
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
