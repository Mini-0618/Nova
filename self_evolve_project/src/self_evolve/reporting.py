from __future__ import annotations

from pathlib import Path

from self_evolve.models import CycleResult


def write_cycle_report(result: CycleResult, cycle_dir: str | Path) -> None:
    p = Path(cycle_dir) / "cycle_report.md"

    text = f'''# Cycle {result.cycle}

## Scores
- baseline_score: {result.baseline_score}
- candidate_score: {result.candidate_score}
- improved: {result.improved}
- promoted: {result.promoted}

## Files
- baseline_eval: `{result.baseline_eval}`
- candidate_eval: `{result.candidate_eval}`
- lessons: `{result.lessons}`
- candidate_prompt: `{result.candidate_prompt}`
'''

    p.write_text(text, encoding="utf-8")


def write_final_report(results: list[CycleResult], reports_dir: str | Path) -> None:
    lines = []
    lines.append("# Self Evolution Final Report")
    lines.append("")
    lines.append(f"- total_cycles: {len(results)}")
    lines.append("")

    for item in results:
        lines.append(
            f"- cycle {item.cycle}: baseline={item.baseline_score}, "
            f"candidate={item.candidate_score}, promoted={item.promoted}"
        )

    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    Path(reports_dir, "final_report.md").write_text("\n".join(lines), encoding="utf-8")
