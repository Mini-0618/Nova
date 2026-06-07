"""
Codex-Local Eval Terminal UI v2
Clean ASCII dashboard for any terminal.

Usage:
    python data/eval/tui.py                    # Dashboard
    python data/eval/tui.py --run              # Run eval offline
    python data/eval/tui.py --run-llm          # Run eval with LLM
    python data/eval/tui.py --report latest    # View latest report
    python data/eval/tui.py --compare r1 r2    # Compare reports
    python data/eval/tui.py -i                 # Interactive mode
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.align import Align
from rich.rule import Rule
from rich import box

EVAL_DIR = Path(__file__).resolve().parent
TASKS_FILE = EVAL_DIR / "tasks.json"
REPORTS_DIR = EVAL_DIR / "reports"
LESSONS_FILE = EVAL_DIR / "lessons.json"

console = Console(width=88)


def load_tasks():
    with open(TASKS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_report(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_latest_report():
    reports = sorted(REPORTS_DIR.glob("eval-*.json"), reverse=True)
    return str(reports[0]) if reports else None


def load_lessons_count():
    if not LESSONS_FILE.exists():
        return 0
    with open(LESSONS_FILE, 'r', encoding='utf-8') as f:
        return len(json.load(f))


def bar(rate, width=20):
    filled = int(rate / 100 * width)
    return f"[green]{'#' * filled}[/][dim]{'.' * (width - filled)}[/]"


def rate_color(rate):
    if rate >= 80: return "green"
    if rate >= 60: return "yellow"
    return "red"


def pct(rate):
    c = rate_color(rate)
    return f"[bold {c}]{rate:.0f}[/]%"


def hr(style="dim"):
    return Rule(style=style)


def render_header():
    t = Text()
    t.append(" codex-local ", style="bold white on dark_blue")
    t.append("  EVAL ", style="bold cyan")
    t.append("DASHBOARD", style="bold white")
    t.append(f"  {datetime.now().strftime('%H:%M')}", style="dim")
    return t


def render_metrics(report):
    total = report.get("total_tasks", 0)
    passed = report.get("passed", 0)
    failed = report.get("failed", 0)
    rate = report.get("pass_rate", 0)

    t = Table(box=None, show_header=False, show_edge=False, padding=(0, 2))
    t.add_column("", justify="center")
    t.add_column("", justify="center")
    t.add_column("", justify="center")
    t.add_column("", justify="center")

    t.add_row(
        f"[bold white]{total}[/]\n[dim]tasks[/]",
        f"[bold green]{passed}[/]\n[dim]passed[/]",
        f"[bold red]{failed}[/]\n[dim]failed[/]",
        f"{pct(rate)}\n[dim]rate[/]",
    )
    return Panel(t, border_style="cyan", box=box.ROUNDED, padding=(0, 2))


def render_categories(report):
    by_cat = report.get("by_category", {})
    if not by_cat:
        return Text("  No data", style="dim")

    t = Table(box=None, show_header=True, header_style="dim",
              show_edge=False, padding=(0, 1))
    t.add_column("", style="bold", min_width=14)
    t.add_column("", min_width=22)
    t.add_column("", justify="right", min_width=5)
    t.add_column("", justify="right", style="dim", min_width=5)

    for cat, stats in sorted(by_cat.items()):
        rate = stats.get("pass_rate", 0)
        p = stats.get("passed", 0)
        tot = stats.get("total", 0)
        c = rate_color(rate)
        t.add_row(f"  {cat}", bar(rate), f"[{c}]{rate:.0f}%[/]", f"{p}/{tot}")
    return t


def render_difficulties(report):
    by_diff = report.get("by_difficulty", {})
    if not by_diff:
        return Text("  No data", style="dim")

    t = Table(box=None, show_header=True, header_style="dim",
              show_edge=False, padding=(0, 1))
    t.add_column("", style="bold", min_width=14)
    t.add_column("", min_width=22)
    t.add_column("", justify="right", min_width=5)
    t.add_column("", justify="right", style="dim", min_width=5)

    icons = {"easy": "+", "medium": "~", "hard": "!"}
    for d in ["easy", "medium", "hard"]:
        stats = by_diff.get(d)
        if not stats:
            continue
        rate = stats.get("pass_rate", 0)
        p = stats.get("passed", 0)
        tot = stats.get("total", 0)
        c = rate_color(rate)
        icon = icons.get(d, " ")
        t.add_row(f"  {icon} {d}", bar(rate), f"[{c}]{rate:.0f}%[/]", f"{p}/{tot}")
    return t


def render_failures(report, max_items=10):
    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed")]

    if not failures:
        return Panel(
            Align.center(Text("All clear. No failures.", style="bold green")),
            border_style="green", box=box.ROUNDED,
            title="[bold green]Failures[/]"
        )

    t = Table(box=None, show_header=True, header_style="dim",
              show_edge=False, padding=(0, 1))
    t.add_column("ID", style="bold", width=5)
    t.add_column("Cat", style="dim", width=12)
    t.add_column("Diff", width=7)
    t.add_column("Title", min_width=20)
    t.add_column("Error", min_width=15)

    for r in failures[:max_items]:
        d = r.get("difficulty", "")
        dc = {"easy": "green", "medium": "yellow", "hard": "red"}.get(d, "white")
        err = (r.get("error") or r.get("details") or "")[:50].replace("\n", " ")
        t.add_row(
            r["task_id"],
            r.get("category", ""),
            Text(d, style=dc),
            r.get("title", ""),
            Text(err, style="red")
        )

    if len(failures) > max_items:
        t.add_row("...", "", "", f"[dim]+{len(failures) - max_items} more[/]", "")

    return Panel(t, border_style="red", box=box.ROUNDED,
                 title=f"[bold red]Failures ({len(failures)})[/]")


def render_task_detail(task, result=None):
    console.print()
    console.print(Rule(f"[bold cyan]{task['id']}[/]  {task['title']}", style="cyan"))
    console.print()

    info = Table(box=None, show_header=False, show_edge=False, padding=(0, 2))
    info.add_column("", style="dim")
    info.add_column("")
    info.add_row("  Category", task["category"])
    info.add_row("  Difficulty", task["difficulty"])
    info.add_row("  Tools", ", ".join(task.get("expected_tools", [])))
    console.print(info)

    console.print()
    console.print(Panel(
        Text(task["task"], style="white"),
        border_style="cyan", box=box.ROUNDED,
        title="[dim]Task[/]"
    ))

    if task.get("setup_files"):
        console.print()
        for path in task["setup_files"]:
            console.print(f"  [dim]setup:[/] {path}")

    if result:
        console.print()
        s = "[green]PASS[/]" if result.get("passed") else "[red]FAIL[/]"
        console.print(f"  Status: {s}")
        if result.get("error"):
            console.print(f"  Error:  [red]{result['error']}[/]")
        if result.get("details"):
            console.print(f"  Detail: {result['details']}")
        if result.get("duration_s"):
            console.print(f"  Time:   {result['duration_s']}s")

    console.print()


def render_compare(r1, r2, p1, p2):
    console.print()
    console.print(Rule("[bold]Report Comparison[/]", style="cyan"))
    console.print()

    name1 = Path(p1).stem.replace("eval-", "")
    name2 = Path(p2).stem.replace("eval-", "")

    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
              title="Summary", title_style="bold")
    t.add_column("", style="bold")
    t.add_column(name1, justify="right")
    t.add_column(name2, justify="right")
    t.add_column("", justify="right")

    r1r = r1.get("pass_rate", 0)
    r2r = r2.get("pass_rate", 0)
    d = r2r - r1r
    ds = "green" if d > 0 else "red" if d < 0 else "dim"
    dp = "+" if d > 0 else ""

    t.add_row("Rate", f"{r1r}%", f"{r2r}%", f"[{ds}]{dp}{d}%[/]")
    t.add_row("Pass", str(r1.get("passed", 0)), str(r2.get("passed", 0)), "")
    t.add_row("Fail", str(r1.get("failed", 0)), str(r2.get("failed", 0)), "")
    console.print(t)

    all_cats = set()
    all_cats.update(r1.get("by_category", {}).keys())
    all_cats.update(r2.get("by_category", {}).keys())

    if all_cats:
        ct = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                   title="Category Delta", title_style="bold")
        ct.add_column("", style="bold")
        ct.add_column("Before", justify="right")
        ct.add_column("After", justify="right")
        ct.add_column("", justify="right")

        for cat in sorted(all_cats):
            v1 = r1.get("by_category", {}).get(cat, {}).get("pass_rate", 0)
            v2 = r2.get("by_category", {}).get(cat, {}).get("pass_rate", 0)
            dd = v2 - v1
            dds = "green" if dd > 0 else "red" if dd < 0 else "dim"
            ddp = "+" if dd > 0 else ""
            ct.add_row(cat, f"{v1}%", f"{v2}%", f"[{dds}]{ddp}{dd}%[/]")
        console.print(ct)

    r1m = {r["task_id"]: r for r in r1.get("results", [])}
    r2m = {r["task_id"]: r for r in r2.get("results", [])}
    gained = [tid for tid in r1m if tid in r2m and not r1m[tid].get("passed") and r2m[tid].get("passed")]
    lost = [tid for tid in r1m if tid in r2m and r1m[tid].get("passed") and not r2m[tid].get("passed")]

    if gained or lost:
        ch = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
                   title="Changes", title_style="bold")
        ch.add_column("Task", style="bold")
        ch.add_column("Change")
        for tid in gained:
            ch.add_row(tid, "[green]FAIL -> PASS[/]")
        for tid in lost:
            ch.add_row(tid, "[red]PASS -> FAIL[/]")
        console.print(ch)

    console.print()


def run_eval_live(tasks, use_llm=False):
    console.print()
    mode = "[cyan]LLM[/]" if use_llm else "[dim]Offline[/]"
    console.print(Rule(f"[bold]Running Eval  {mode}[/]", style="cyan"))
    console.print()

    results = []

    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=20, complete_style="green", finished_style="bold green"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        prog = progress.add_task("[cyan]eval", total=len(tasks))

        for task in tasks:
            tid = task["id"]
            title = task["title"][:30]
            progress.update(prog, description=f"[bold]{tid}[/] {title}")

            if use_llm:
                from run_eval import run_task_with_loop
                result = asyncio.run(run_task_with_loop(task))
            else:
                from run_eval import run_task_subprocess
                result = run_task_subprocess(task)

            results.append(result)

            mark = "[green bold]OK[/]" if result.passed else "[red bold]XX[/]"
            dc = {"easy": "green", "medium": "yellow", "hard": "red"}.get(task["difficulty"], "dim")
            console.print(f"    {mark}  [{dc}]{task['difficulty']:6s}[/] [bold]{tid}[/] {task['title'][:38]}")

            progress.advance(prog)

    from run_eval import build_report
    from dataclasses import asdict
    report = build_report(results)
    rd = asdict(report) if hasattr(report, '__dataclass_fields__') else report

    console.print()
    console.print(render_metrics(rd))
    console.print()

    if any(not r.passed for r in results):
        console.print(render_failures(rd))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rp = REPORTS_DIR / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    with open(rp, 'w', encoding='utf-8') as fh:
        json.dump(rd, fh, indent=2, ensure_ascii=False)
    console.print(f"\n  [dim]Saved:[/] {rp.name}")


def dashboard(report=None):
    console.print()
    console.print(render_header())
    console.print()

    tasks = load_tasks()

    if report:
        console.print(render_metrics(report))
        console.print()

        left = render_categories(report)
        right = render_difficulties(report)

        grid = Table(box=None, show_header=False, show_edge=False, padding=0)
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(
            Panel(left, title="[bold]Category[/]", border_style="dim", box=box.ROUNDED),
            Panel(right, title="[bold]Difficulty[/]", border_style="dim", box=box.ROUNDED),
        )
        console.print(grid)
        console.print()
        console.print(render_failures(report))
    else:
        console.print(Panel(
            Text("No report yet. Press 'r' to run offline eval, 'R' for LLM eval.", style="dim"),
            border_style="dim", box=box.ROUNDED
        ))

    console.print()

    help_t = Text()
    help_t.append("  q", style="bold cyan")
    help_t.append(" quit ", style="dim")
    help_t.append("r", style="bold cyan")
    help_t.append(" run ", style="dim")
    help_t.append("R", style="bold cyan")
    help_t.append(" run-llm ", style="dim")
    help_t.append("l", style="bold cyan")
    help_t.append(" latest ", style="dim")
    help_t.append("f", style="bold cyan")
    help_t.append(" failures ", style="dim")
    help_t.append("t <id>", style="bold cyan")
    help_t.append(" task ", style="dim")
    help_t.append("c", style="bold cyan")
    help_t.append(" compare", style="dim")

    console.print(Panel(help_t, border_style="dim", box=box.ROUNDED))
    console.print()


def interactive():
    tasks = load_tasks()
    report = None
    latest = find_latest_report()
    if latest:
        report = load_report(latest)

    console.clear()
    dashboard(report)

    while True:
        try:
            cmd = console.input("[bold cyan]> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break

        low = cmd.lower()

        if low == "q":
            break
        elif low == "r":
            run_eval_live(tasks, use_llm=False)
        elif low == "r!":
            run_eval_live(tasks, use_llm=True)
        elif low == "l":
            lp = find_latest_report()
            if lp:
                report = load_report(lp)
                dashboard(report)
            else:
                console.print("  [yellow]No reports found.[/]")
        elif low == "f":
            if report:
                console.print(render_failures(report, max_items=30))
            else:
                console.print("  [yellow]No report loaded.[/]")
        elif low.startswith("t "):
            tid = cmd[2:].strip().upper()
            task = next((t for t in tasks if t["id"] == tid), None)
            if task:
                res = None
                if report:
                    res = next((r for r in report.get("results", []) if r["task_id"] == tid), None)
                render_task_detail(task, res)
            else:
                console.print(f"  [yellow]Task {tid} not found.[/]")
        elif low == "c":
            reports = sorted(REPORTS_DIR.glob("eval-*.json"), reverse=True)
            if len(reports) >= 2:
                r1 = load_report(str(reports[1]))
                r2 = load_report(str(reports[0]))
                render_compare(r1, r2, str(reports[1]), str(reports[0]))
            else:
                console.print("  [yellow]Need at least 2 reports.[/]")
        elif low == "lessons":
            count = load_lessons_count()
            console.print(f"  [cyan]{count}[/] lessons loaded")
        elif low == "?" or low == "help":
            console.clear()
            dashboard(report)
        else:
            console.print(f"  [dim]Unknown: {cmd}[/]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-llm", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--compare", nargs=2)
    parser.add_argument("--task")
    parser.add_argument("--failures", action="store_true")
    parser.add_argument("-i", "--interactive", action="store_true")
    args = parser.parse_args()

    if args.interactive:
        interactive()
    elif args.run:
        run_eval_live(load_tasks(), use_llm=False)
    elif args.run_llm:
        run_eval_live(load_tasks(), use_llm=True)
    elif args.report:
        p = find_latest_report() if args.report == "latest" else args.report
        if p:
            dashboard(load_report(p))
        else:
            console.print("[red]No reports.[/]")
    elif args.compare:
        r1, r2 = load_report(args.compare[0]), load_report(args.compare[1])
        render_compare(r1, r2, args.compare[0], args.compare[1])
    elif args.task:
        tasks = load_tasks()
        task = next((t for t in tasks if t["id"] == args.task.upper()), None)
        if task:
            render_task_detail(task)
        else:
            console.print(f"[red]Task {args.task} not found.[/]")
    elif args.failures:
        p = find_latest_report()
        if p:
            console.print(render_failures(load_report(p), max_items=50))
        else:
            console.print("[red]No reports.[/]")
    else:
        latest = find_latest_report()
        report = load_report(latest) if latest else None
        dashboard(report)


if __name__ == "__main__":
    main()
