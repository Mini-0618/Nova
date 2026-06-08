from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from self_evolve.config import ensure_dirs, load_config
from self_evolve.models import CycleResult, StepResult
from self_evolve.prompts import PromptManager
from self_evolve.reporting import write_cycle_report, write_final_report
from self_evolve.runner import CommandRunner
from self_evolve.scoring import ScoreExtractor
from self_evolve.store import JsonlStore


class SelfEvolutionLoop:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config = load_config(self.config_path)
        self.paths = ensure_dirs(self.config)

        self.runner = CommandRunner(timeout_sec=float(self.config.get("timeout_sec", 120)))
        self.scorer = ScoreExtractor(self.config.get("score_keys"))
        self.prompt_manager = PromptManager(self.config["current_prompt"])

        self.loop_log = JsonlStore(self.paths["logs"] / "loop.jsonl")
        self.step_log = JsonlStore(self.paths["logs"] / "steps.jsonl")

    def render(self, template: str, values: dict[str, Any]) -> str:
        return template.format(**values)

    def log_step(self, step: StepResult) -> None:
        self.step_log.append(asdict(step))

    def require_ok(self, step: StepResult) -> None:
        self.log_step(step)

        if not step.ok:
            raise RuntimeError(
                f"step failed: {step.name}\n"
                f"command: {step.command}\n"
                f"returncode: {step.returncode}\n"
                f"stderr: {step.stderr}"
            )

    def run_once(self, cycle: int) -> CycleResult:
        cycle_dir = self.paths["cycles"] / f"cycle_{cycle:04d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        current_prompt = Path(self.config["current_prompt"])

        baseline_task_out = cycle_dir / "baseline_tasks.jsonl"
        baseline_eval_out = cycle_dir / "baseline_eval.json"
        lessons_out = cycle_dir / "lessons.json"

        candidate_prompt = cycle_dir / "candidate_prompt.md"
        candidate_task_out = cycle_dir / "candidate_tasks.jsonl"
        candidate_eval_out = cycle_dir / "candidate_eval.json"

        commands = self.config["commands"]

        base_values = {
            "python": sys.executable,
            "cycle": cycle,
            "prompt": str(current_prompt),
            "task_out": str(baseline_task_out),
            "eval_out": str(baseline_eval_out),
            "lessons_out": str(lessons_out),
            "candidate_prompt": str(candidate_prompt),
        }

        step = self.runner.run("baseline.run_task", self.render(commands["run_task"], base_values))
        self.require_ok(step)

        step = self.runner.run("baseline.eval", self.render(commands["eval"], base_values))
        self.require_ok(step)

        baseline_score = self.scorer.extract_from_file(baseline_eval_out).score

        step = self.runner.run("analyze_failure", self.render(commands["analyze_failure"], base_values))
        self.require_ok(step)

        step = self.runner.run("improve_prompt", self.render(commands["improve_prompt"], base_values))
        self.require_ok(step)

        cand_values = {
            "python": sys.executable,
            "cycle": cycle,
            "prompt": str(candidate_prompt),
            "task_out": str(candidate_task_out),
            "eval_out": str(candidate_eval_out),
            "lessons_out": str(lessons_out),
            "candidate_prompt": str(candidate_prompt),
        }

        step = self.runner.run("candidate.run_task", self.render(commands["run_task"], cand_values))
        self.require_ok(step)

        step = self.runner.run("candidate.eval", self.render(commands["eval"], cand_values))
        self.require_ok(step)

        candidate_score = self.scorer.extract_from_file(candidate_eval_out).score

        min_improve = float(self.config.get("min_improve", 0.01))
        improved = candidate_score > baseline_score + min_improve
        promoted = False

        if improved:
            self.prompt_manager.promote(candidate_prompt)
            promoted = True

        result = CycleResult(
            cycle=cycle,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            improved=improved,
            promoted=promoted,
            baseline_eval=str(baseline_eval_out),
            candidate_eval=str(candidate_eval_out),
            lessons=str(lessons_out),
            candidate_prompt=str(candidate_prompt),
            created_at=time.time(),
        )

        self.loop_log.append(asdict(result))
        write_cycle_report(result, cycle_dir)
        return result

    def run_loop(self, cycles: int) -> list[CycleResult]:
        results: list[CycleResult] = []

        for cycle in range(1, cycles + 1):
            print(f"===== cycle {cycle} =====")

            try:
                result = self.run_once(cycle)
                results.append(result)
                print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
            except Exception as exc:
                self.loop_log.append(
                    {
                        "cycle": cycle,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "created_at": time.time(),
                    }
                )
                print(f"cycle failed: {exc}")
                break

        write_final_report(results, self.paths["reports"])
        return results
