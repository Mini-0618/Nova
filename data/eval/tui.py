"""
Codex-Local Eval Terminal UI
Interactive dashboard for running evals, viewing results, and tracking improvement.

Usage:
    python data/eval/tui.py                    # Interactive dashboard
    python data/eval/tui.py --run              # Run eval with live display
    python data/eval/tui.py --report latest    # View latest report
    python data/eval/tui.py --report FILE      # View specific report
    python data/eval/tui.py --compare r1.json r2.json  # Compare two reports
"""

import os
import sys
import json
import time
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.columns import Columns
from rich.align import Align
from rich.rule import Rule
from rich.style import Style
from rich.markdown import Markdown
from rich.tree import Tree
from rich import box

EVAL_DIR = Path(__file__).resolve().parent
TASKS_FILE = EVAL_DIR / "tasks.json"
REPORTS_DIR = EVAL_DIR / "reports"
LESSONS_FILE = EVAL_DIR / "lessons.json"

console = Console()

# ── Styles ──────────────────────────────────────────────────────

STYLES = {
    "header": Style(bold=True, color="cyan"),
    "pass": Style(color="green", bold=True),
    "fail": Style(color="red", bold=True),
    "skip": Style(color="yellow"),
    "dim": Style(dim=True),
    "highlight": Style(color="cyan", bold=True),
    "warn": Style(color="yellow", bold=True),
    "category": Style(color="magenta"),
    "difficulty": {
        "easy": Style(color="green"),
        "medium": Style(color="yellow"),
        "hard": Style(color="red", bold=True),
    },
}


def load_tasks() -> List[Dict[str, Any]]:
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_report(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_latest_report() -> Optional[str]:
    reports = sorted(REPORTS_DIR.glob("eval-*.json"), reverse=True)
    return str(reports[0]) if reports else None


def load_lessons_count() -> int:
    if not LESSONS_FILE.exists():
        return 0
    with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
        return len(json.load(f))


# ── Components ──────────────────────────────────────────────────

def make_header() -> Panel:
    """Top banner."""
    title = Text()
    title.append("  CODEX-LOCAL ", style="bold white on blue")
    title.append("  Eval Dashboard", style="bold cyan")
    title.append(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}", style="dim")
    return Panel(title, box=box.DOUBLE, style="blue")


def make_task_overview(tasks: List[Dict]) -> Panel:
    """Category and difficulty breakdown of all tasks."""
    cats = {}
    diffs = {}
    for t in tasks:
        cat = t["category"]
        diff = t["difficulty"]
        cats[cat] = cats.get(cat, 0) + 1
        diffs[diff] = diffs.get(diff, 0) + 1

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Label", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("[cyan]Total Tasks[/]", f"[bold]{len(tasks)}[/]")
    table.add_row("", "")

    # Categories
    for cat, count in sorted(cats.items()):
        pct = count / len(tasks) * 100
        bar = f"[green]{'#' * int(pct / 5)}[/][dim]{'.' * (20 - int(pct / 5))}[/]"
        table.add_row(f"  {cat}", f"{bar} {count}")

    table.add_row("", "")

    # Difficulties
    diff_colors = {"easy": "green", "medium": "yellow", "hard": "red"}
    for diff in ["easy", "medium", "hard"]:
        count = diffs.get(diff, 0)
        color = diff_colors.get(diff, "white")
        pct = count / len(tasks) * 100
        bar = f"[{color}]{'#' * int(pct / 5)}[/][dim]{'.' * (20 - int(pct / 5))}[/]"
        table.add_row(f"  {diff}", f"{bar} {count}")

    return Panel(table, title="[bold]Task Inventory[/]", border_style="cyan", box=box.ROUNDED)


def make_report_summary(report: Dict) -> Panel:
    """High-level metrics from a report."""
    passed = report.get("passed", 0)
    failed = report.get("failed", 0)
    total = report.get("total_tasks", 0)
    rate = report.get("pass_rate", 0)

    # Color the pass rate
    if rate >= 80:
        rate_style = "bold green"
    elif rate >= 60:
        rate_style = "bold yellow"
    else:
        rate_style = "bold red"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Pass Rate", f"[{rate_style}]{rate}%[/]")
    table.add_row("Passed", f"[green]{passed}[/]")
    table.add_row("Failed", f"[red]{failed}[/]")
    table.add_row("Total", f"[bold]{total}[/]")

    # Extra metrics if available
    if report.get("tool_call_accuracy"):
        table.add_row("Tool Accuracy", f"{report['tool_call_accuracy']}%")
    if report.get("regression_rate") is not None:
        table.add_row("Regressions", f"{report['regression_rate']}%")
    if report.get("timestamp"):
        table.add_row("Time", f"[dim]{report['timestamp']}[/]")

    return Panel(table, title="[bold]Report Summary[/]", border_style="green", box=box.ROUNDED)


def make_category_breakdown(report: Dict) -> Panel:
    """Pass rate per category as a visual bar chart."""
    by_cat = report.get("by_category", {})

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Category", style="bold", min_width=15)
    table.add_column("Bar", min_width=22)
    table.add_column("Pass", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Rate", justify="right", min_width=6)

    for cat, stats in sorted(by_cat.items()):
        rate = stats.get("pass_rate", 0)
        p = stats.get("passed", 0)
        t = stats.get("total", 0)

        if rate >= 80:
            color = "green"
        elif rate >= 60:
            color = "yellow"
        else:
            color = "red"

        bar_filled = int(rate / 5)
        bar = f"[{color}]{'#' * bar_filled}[/][dim]{'.' * (20 - bar_filled)}[/]"
        table.add_row(cat, bar, f"[green]{p}[/]", str(t), f"[{color}]{rate}%[/]")

    return Panel(table, title="[bold]By Category[/]", border_style="magenta", box=box.ROUNDED)


def make_difficulty_breakdown(report: Dict) -> Panel:
    """Pass rate per difficulty."""
    by_diff = report.get("by_difficulty", {})

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Difficulty", style="bold", min_width=10)
    table.add_column("Bar", min_width=22)
    table.add_column("Pass", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Rate", justify="right", min_width=6)

    diff_order = ["easy", "medium", "hard"]
    diff_colors = {"easy": "green", "medium": "yellow", "hard": "red"}

    for diff in diff_order:
        stats = by_diff.get(diff, {})
        if not stats:
            continue
        rate = stats.get("pass_rate", 0)
        p = stats.get("passed", 0)
        t = stats.get("total", 0)
        color = diff_colors.get(diff, "white")

        bar_filled = int(rate / 5)
        bar = f"[{color}]{'#' * bar_filled}[/][dim]{'.' * (20 - bar_filled)}[/]"
        table.add_row(diff, bar, f"[green]{p}[/]", str(t), f"[{color}]{rate}%[/]")

    return Panel(table, title="[bold]By Difficulty[/]", border_style="yellow", box=box.ROUNDED)


def make_failures_list(report: Dict, max_items: int = 15) -> Panel:
    """List of failed tasks with details."""
    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed")]

    if not failures:
        return Panel(
            Align.center(Text("No failures!", style="bold green")),
            title="[bold]Failures[/]",
            border_style="green",
            box=box.ROUNDED
        )

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold red", padding=(0, 1))
    table.add_column("ID", style="bold", width=5)
    table.add_column("Category", style="dim", width=12)
    table.add_column("Difficulty", width=8)
    table.add_column("Title", min_width=25)
    table.add_column("Error", min_width=20, max_width=40)

    for r in failures[:max_items]:
        diff_style = STYLES["difficulty"].get(r.get("difficulty", ""), Style())
        error = r.get("error") or r.get("details") or ""
        error = error[:60].replace("\n", " ")

        table.add_row(
            r["task_id"],
            r.get("category", ""),
            Text(r.get("difficulty", ""), style=diff_style),
            r.get("title", ""),
            Text(error, style="red")
        )

    if len(failures) > max_items:
        table.add_row("...", "", "", f"[dim]+{len(failures) - max_items} more[/]", "")

    return Panel(table, title=f"[bold red]Failures ({len(failures)})[/]", border_style="red", box=box.ROUNDED)


def make_lessons_info() -> Panel:
    """Show lessons.json status."""
    count = load_lessons_count()

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Lessons", f"[cyan]{count}[/]")
    table.add_row("File", f"[dim]{LESSONS_FILE.name}[/]")

    if count > 0:
        with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
            lessons = json.load(f)
        cats = set(l.get("category", "") for l in lessons)
        table.add_row("Categories", ", ".join(sorted(cats)))
        avg_conf = sum(l.get("confidence", 0) for l in lessons) / count
        table.add_row("Avg Confidence", f"{avg_conf:.0%}")

    return Panel(table, title="[bold]Lessons[/]", border_style="cyan", box=box.ROUNDED)


def make_commands_help() -> Panel:
    """Show available commands."""
    text = Text()
    text.append("  q", style="bold cyan")
    text.append("  Quit\n", style="dim")
    text.append("  r", style="bold cyan")
    text.append("  Run eval (offline)\n", style="dim")
    text.append("  R", style="bold cyan")
    text.append("  Run eval (LLM)\n", style="dim")
    text.append("  l", style="bold cyan")
    text.append("  View latest report\n", style="dim")
    text.append("  f", style="bold cyan")
    text.append("  Show failures\n", style="dim")
    text.append("  c", style="bold cyan")
    text.append("  Compare reports\n", style="dim")
    text.append("  s", style="bold cyan")
    text.append("  Self-improve loop\n", style="dim")
    text.append("  ?", style="bold cyan")
    text.append("  This help", style="dim")

    return Panel(text, title="[bold]Commands[/]", border_style="blue", box=box.ROUNDED)


# ── Full Dashboards ─────────────────────────────────────────────

def dashboard_main(tasks: List[Dict], report: Optional[Dict] = None):
    """Main dashboard view."""
    layout = Layout()
    layout.split_column(
        Layout(make_header(), size=3),
        Layout(name="body"),
        Layout(make_commands_help(), size=12),
    )

    if report:
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=2),
        )
        layout["left"].split_column(
            Layout(make_report_summary(report), size=12),
            Layout(make_lessons_info(), size=10),
            Layout(make_task_overview(tasks)),
        )
        layout["right"].split_column(
            Layout(make_category_breakdown(report)),
            Layout(make_difficulty_breakdown(report)),
        )
    else:
        layout["body"].split_row(
            Layout(make_task_overview(tasks)),
            Layout(make_lessons_info()),
        )

    console.print(layout)


def dashboard_report(report: Dict):
    """Detailed report view."""
    console.print()
    console.print(make_header())
    console.print()

    # Summary row
    console.print(Columns([
        make_report_summary(report),
        make_lessons_info(),
    ], padding=2))

    console.print()

    # Breakdowns
    console.print(Columns([
        make_category_breakdown(report),
        make_difficulty_breakdown(report),
    ], padding=2))

    console.print()

    # Failures
    console.print(make_failures_list(report))

    console.print()


def dashboard_compare(report1: Dict, report2: Dict, path1: str, path2: str):
    """Side-by-side comparison of two reports."""
    console.print()
    console.print(Rule("[bold cyan]Report Comparison[/]"))
    console.print()

    # Summary comparison
    table = Table(box=box.ROUNDED, title="Summary Comparison", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column(f"Before\n{Path(path1).stem}", justify="right")
    table.add_column(f"After\n{Path(path2).stem}", justify="right")
    table.add_column("Delta", justify="right")

    r1_rate = report1.get("pass_rate", 0)
    r2_rate = report2.get("pass_rate", 0)
    delta = r2_rate - r1_rate
    delta_style = "green" if delta > 0 else "red" if delta < 0 else "dim"
    delta_sign = "+" if delta > 0 else ""

    table.add_row("Pass Rate", f"{r1_rate}%", f"{r2_rate}%", f"[{delta_style}]{delta_sign}{delta}%[/]")
    table.add_row("Passed", str(report1.get("passed", 0)), str(report2.get("passed", 0)), "")
    table.add_row("Failed", str(report1.get("failed", 0)), str(report2.get("failed", 0)), "")
    table.add_row("Total", str(report1.get("total_tasks", 0)), str(report2.get("total_tasks", 0)), "")

    console.print(table)
    console.print()

    # Category comparison
    cat_table = Table(box=box.ROUNDED, title="Category Comparison", show_header=True, header_style="bold cyan")
    cat_table.add_column("Category", style="bold")
    cat_table.add_column("Before", justify="right")
    cat_table.add_column("After", justify="right")
    cat_table.add_column("Delta", justify="right")

    all_cats = set()
    all_cats.update(report1.get("by_category", {}).keys())
    all_cats.update(report2.get("by_category", {}).keys())

    for cat in sorted(all_cats):
        r1 = report1.get("by_category", {}).get(cat, {}).get("pass_rate", 0)
        r2 = report2.get("by_category", {}).get(cat, {}).get("pass_rate", 0)
        d = r2 - r1
        ds = "green" if d > 0 else "red" if d < 0 else "dim"
        dp = "+" if d > 0 else ""
        cat_table.add_row(cat, f"{r1}%", f"{r2}%", f"[{ds}]{dp}{d}%[/]")

    console.print(cat_table)

    # Newly passing / newly failing
    r1_results = {r["task_id"]: r for r in report1.get("results", [])}
    r2_results = {r["task_id"]: r for r in report2.get("results", [])}

    newly_passing = []
    newly_failing = []
    for tid in r1_results:
        if tid in r2_results:
            was = r1_results[tid].get("passed", False)
            now = r2_results[tid].get("passed", False)
            if not was and now:
                newly_passing.append(tid)
            elif was and not now:
                newly_failing.append(tid)

    if newly_passing or newly_failing:
        console.print()
        changes = Table(box=box.ROUNDED, title="Task-Level Changes", show_header=True)
        changes.add_column("Task ID", style="bold")
        changes.add_column("Change")

        for tid in newly_passing:
            changes.add_row(tid, "[green]FAIL -> PASS[/]")
        for tid in newly_failing:
            changes.add_row(tid, "[red]PASS -> FAIL[/]")

        console.print(changes)

    console.print()


def view_task_detail(task: Dict, result: Optional[Dict] = None):
    """Show detailed info for a single task."""
    console.print()
    console.print(Rule(f"[bold]{task['id']}: {task['title']}[/]"))
    console.print()

    info = Table(box=box.SIMPLE, show_header=False)
    info.add_column("Key", style="bold")
    info.add_column("Value")
    info.add_row("ID", task["id"])
    info.add_row("Category", task["category"])
    info.add_row("Difficulty", task["difficulty"])
    info.add_row("Expected Tools", ", ".join(task.get("expected_tools", [])))
    console.print(info)

    console.print()
    console.print(Panel(task["task"], title="Task Description", border_style="cyan"))

    if task.get("setup_files"):
        console.print()
        console.print("[bold]Setup Files:[/]")
        for path in task["setup_files"]:
            console.print(f"  {path}")

    if result:
        console.print()
        status = "[green]PASS[/]" if result.get("passed") else "[red]FAIL[/]"
        console.print(f"  Status: {status}")
        if result.get("error"):
            console.print(f"  Error: [red]{result['error']}[/]")
        if result.get("details"):
            console.print(f"  Details: {result['details']}")
        if result.get("duration_s"):
            console.print(f"  Duration: {result['duration_s']}s")

    console.print()


# ── Interactive Mode ────────────────────────────────────────────

def interactive_mode():
    """Interactive dashboard with command input."""
    tasks = load_tasks()
    current_report = None

    # Try loading latest report
    latest = find_latest_report()
    if latest:
        current_report = load_report(latest)

    console.clear()
    dashboard_main(tasks, current_report)

    while True:
        console.print()
        try:
            cmd = console.input("[bold cyan]> [/]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "q":
            break

        elif cmd == "r":
            run_eval_live(tasks, use_llm=False)

        elif cmd == "R":
            run_eval_live(tasks, use_llm=True)

        elif cmd == "l":
            latest = find_latest_report()
            if latest:
                current_report = load_report(latest)
                dashboard_report(current_report)
            else:
                console.print("[yellow]No reports found.[/]")

        elif cmd == "f":
            if current_report:
                console.print(make_failures_list(current_report, max_items=30))
            else:
                console.print("[yellow]No report loaded. Press 'l' first.[/]")

        elif cmd.startswith("t "):
            tid = cmd[2:].strip().upper()
            task = next((t for t in tasks if t["id"] == tid), None)
            if task:
                result = None
                if current_report:
                    result = next((r for r in current_report.get("results", []) if r["task_id"] == tid), None)
                view_task_detail(task, result)
            else:
                console.print(f"[yellow]Task {tid} not found.[/]")

        elif cmd == "s":
            console.print("[cyan]Starting self-improvement loop...[/]")
            os.system(f'cd /d codex-local && python data/eval/self_improve_loop.py --dry-run')

        elif cmd == "?":
            console.print(make_commands_help())

        else:
            console.print(f"[dim]Unknown command: {cmd}. Press '?' for help.[/]")


# ── Live Eval Runner ────────────────────────────────────────────

def run_eval_live(tasks: List[Dict], use_llm: bool = False):
    """Run eval with live progress display."""
    from dataclasses import asdict

    console.print()
    mode = "LLM" if use_llm else "Offline"
    console.print(Rule(f"[bold]Running Eval ({mode} Mode)[/]"))
    console.print()

    results = []
    passed = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_progress = progress.add_task("[cyan]Evaluating...", total=len(tasks))

        for i, task in enumerate(tasks):
            # Update progress description
            progress.update(task_progress, description=f"[cyan]{task['id']}[/] {task['title'][:35]}...")

            if use_llm:
                # Run with LLM
                import asyncio
                from run_eval import run_task_with_loop
                result = asyncio.run(run_task_with_loop(task))
            else:
                # Offline: structure check
                from run_eval import run_task_subprocess
                result = run_task_subprocess(task)

            results.append(result)

            if result.passed:
                passed += 1
                status = "[green]PASS[/]"
            else:
                failed += 1
                status = "[red]FAIL[/]"

            # Print result line
            diff_color = {"easy": "green", "medium": "yellow", "hard": "red"}.get(task["difficulty"], "white")
            console.print(
                f"  {status}  [{diff_color}]{task['difficulty']:6s}[/] "
                f"[bold]{task['id']}[/] {task['title'][:45]}"
                f"  [dim]{result.duration_s}s[/]"
            )

            progress.advance(task_progress)

    # Build report
    from run_eval import build_report
    report = build_report(results)
    report_dict = asdict(report) if hasattr(report, '__dataclass_fields__') else report

    console.print()
    console.print(make_report_summary(report_dict))
    console.print()

    if failed > 0:
        console.print(make_failures_list(report_dict))

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)
    console.print(f"\n[dim]Report saved: {report_path}[/]")

    return report


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Codex-Local Eval Terminal UI")
    parser.add_argument("--run", action="store_true", help="Run eval with live display")
    parser.add_argument("--run-llm", action="store_true", help="Run eval with LLM")
    parser.add_argument("--report", help="View a report (path or 'latest')")
    parser.add_argument("--compare", nargs=2, metavar=("R1", "R2"), help="Compare two reports")
    parser.add_argument("--task", help="View task detail (e.g. E11)")
    parser.add_argument("--failures", action="store_true", help="Show failures from latest report")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive dashboard")
    args = parser.parse_args()

    tasks = load_tasks()

    if args.interactive:
        interactive_mode()
    elif args.run:
        run_eval_live(tasks, use_llm=False)
    elif args.run_llm:
        run_eval_live(tasks, use_llm=True)
    elif args.report:
        if args.report == "latest":
            path = find_latest_report()
            if not path:
                console.print("[red]No reports found.[/]")
                return
        else:
            path = args.report
        report = load_report(path)
        dashboard_report(report)
    elif args.compare:
        r1 = load_report(args.compare[0])
        r2 = load_report(args.compare[1])
        dashboard_compare(r1, r2, args.compare[0], args.compare[1])
    elif args.task:
        tid = args.task.upper()
        task = next((t for t in tasks if t["id"] == tid), None)
        if task:
            view_task_detail(task)
        else:
            console.print(f"[red]Task {tid} not found.[/]")
    elif args.failures:
        path = find_latest_report()
        if path:
            report = load_report(path)
            console.print(make_failures_list(report, max_items=50))
        else:
            console.print("[red]No reports found.[/]")
    else:
        # Default: show dashboard
        latest = find_latest_report()
        report = load_report(latest) if latest else None
        dashboard_main(tasks, report)


if __name__ == "__main__":
    main()
