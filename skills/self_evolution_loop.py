"""
Self Evolution Loop
跑任务 -> 评估 -> 分析失败 -> 生成改进 -> 再评估 -> 分数提升则晋级

用法：
    python skills/self_evolution_loop.py --init
    python skills/self_evolution_loop.py --cycles 3
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "workspace": "self_evolution_runs",
    "current_prompt": "prompts/current.md",
    "candidate_prompt": "prompts/candidate.md",
    "min_improve": 0.01,
    "max_cycles": 3,
    "timeout_sec": 600,
    "commands": {
        "run_task": "python -m codex_loop run --prompt {prompt} --out {task_out}",
        "eval": "python -m eval_system run --input {task_out} --out {eval_out}",
        "analyze_failure": "python -m failure_analyzer --eval {eval_out} --out {lessons_out}",
        "improve_prompt": "python -m evolution_system improve --prompt {prompt} --lessons {lessons_out} --out {candidate_prompt}",
    },
    "score_keys": ["score", "accuracy", "pass_rate"],
}


@dataclass
class StepResult:
    name: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    runtime_sec: float
    ok: bool


@dataclass
class CycleResult:
    cycle: int
    baseline_score: float
    candidate_score: float
    improved: bool
    promoted: bool
    baseline_eval: str
    candidate_eval: str
    lessons: str
    candidate_prompt: str
    created_at: float


class SelfEvolutionLoop:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self.config = self.load_config(self.config_path)

        self.workspace = Path(self.config["workspace"])
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.logs_dir = self.workspace / "logs"
        self.cycles_dir = self.workspace / "cycles"
        self.reports_dir = self.workspace / "reports"

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.cycles_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.loop_log = self.logs_dir / "loop.jsonl"
        self.step_log = self.logs_dir / "steps.jsonl"

    @staticmethod
    def load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            raise FileNotFoundError(
                f"配置文件不存在，已生成默认配置：{path}\n"
                f"请先修改里面的命令，再重新运行。"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def append_jsonl(self, path: Path, data: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")

    def render_cmd(self, template: str, values: dict[str, Any]) -> str:
        return template.format(**values)

    def run_command(self, name: str, command: str, cwd: str | Path | None = None) -> StepResult:
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                shlex.split(command),
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=float(self.config.get("timeout_sec", 600)),
            )
            runtime_sec = time.perf_counter() - start
            result = StepResult(
                name=name, command=command, returncode=proc.returncode,
                stdout=proc.stdout[-10000:], stderr=proc.stderr[-10000:],
                runtime_sec=runtime_sec, ok=proc.returncode == 0,
            )
        except subprocess.TimeoutExpired as exc:
            runtime_sec = time.perf_counter() - start
            result = StepResult(
                name=name, command=command, returncode=124,
                stdout=str(exc.stdout or "")[-10000:],
                stderr=str(exc.stderr or "timeout")[-10000:],
                runtime_sec=runtime_sec, ok=False,
            )
        self.append_jsonl(self.step_log, asdict(result))
        return result

    def require_ok(self, result: StepResult) -> None:
        if not result.ok:
            raise RuntimeError(
                f"步骤失败：{result.name}\n命令：{result.command}\n"
                f"returncode：{result.returncode}\nstderr：{result.stderr}"
            )

    def extract_score_from_file(self, path: str | Path) -> float:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(text)
            score = self.extract_score_from_json(data)
            if score is not None:
                return score
        except json.JSONDecodeError:
            pass
        score = self.extract_score_from_text(text)
        if score is None:
            raise ValueError(f"无法从评估文件中提取分数：{p}")
        return score

    def extract_score_from_json(self, data: Any) -> float | None:
        score_keys = self.config.get("score_keys", ["score", "accuracy", "pass_rate"])
        if isinstance(data, dict):
            for key in score_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, (int, float)):
                        return float(value)
            for value in data.values():
                found = self.extract_score_from_json(value)
                if found is not None:
                    return found
        if isinstance(data, list):
            for item in data:
                found = self.extract_score_from_json(item)
                if found is not None:
                    return found
        return None

    def extract_score_from_text(self, text: str) -> float | None:
        patterns = [
            r"score\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"accuracy\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"pass_rate\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def promote_prompt(self, candidate_prompt: Path, current_prompt: Path) -> None:
        if not candidate_prompt.exists():
            raise FileNotFoundError(str(candidate_prompt))
        current_prompt.parent.mkdir(parents=True, exist_ok=True)
        if current_prompt.exists():
            backup = current_prompt.with_suffix(
                current_prompt.suffix + f".bak_{int(time.time())}"
            )
            shutil.copy2(current_prompt, backup)
        shutil.copy2(candidate_prompt, current_prompt)

    def run_once(self, cycle: int) -> CycleResult:
        cycle_dir = self.cycles_dir / f"cycle_{cycle:04d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        current_prompt = Path(self.config["current_prompt"])
        candidate_prompt = Path(self.config["candidate_prompt"])

        baseline_task_out = cycle_dir / "baseline_tasks.jsonl"
        baseline_eval_out = cycle_dir / "baseline_eval.json"
        lessons_out = cycle_dir / "lessons.json"
        candidate_task_out = cycle_dir / "candidate_tasks.jsonl"
        candidate_eval_out = cycle_dir / "candidate_eval.json"
        candidate_prompt_out = cycle_dir / "candidate_prompt.md"

        values = {
            "cycle": cycle,
            "prompt": str(current_prompt),
            "candidate_prompt": str(candidate_prompt_out),
            "task_out": str(baseline_task_out),
            "eval_out": str(baseline_eval_out),
            "lessons_out": str(lessons_out),
        }
        commands = self.config["commands"]

        # 1. 跑当前 prompt 的任务
        cmd = self.render_cmd(commands["run_task"], values)
        self.require_ok(self.run_command("baseline.run_task", cmd))

        # 2. 评估当前结果
        cmd = self.render_cmd(commands["eval"], values)
        self.require_ok(self.run_command("baseline.eval", cmd))
        baseline_score = self.extract_score_from_file(baseline_eval_out)

        # 3. 分析失败，生成 lessons
        cmd = self.render_cmd(commands["analyze_failure"], values)
        self.require_ok(self.run_command("analyze_failure", cmd))

        # 4. 根据 lessons 改进 prompt
        cmd = self.render_cmd(commands["improve_prompt"], values)
        self.require_ok(self.run_command("improve_prompt", cmd))

        # 5. 用新 prompt 再跑一次任务
        candidate_values = {
            "cycle": cycle,
            "prompt": str(candidate_prompt_out),
            "candidate_prompt": str(candidate_prompt_out),
            "task_out": str(candidate_task_out),
            "eval_out": str(candidate_eval_out),
            "lessons_out": str(lessons_out),
        }
        cmd = self.render_cmd(commands["run_task"], candidate_values)
        self.require_ok(self.run_command("candidate.run_task", cmd))

        # 6. 评估新 prompt
        cmd = self.render_cmd(commands["eval"], candidate_values)
        self.require_ok(self.run_command("candidate.eval", cmd))
        candidate_score = self.extract_score_from_file(candidate_eval_out)

        min_improve = float(self.config.get("min_improve", 0.01))
        improved = candidate_score > baseline_score + min_improve
        promoted = False

        if improved:
            self.promote_prompt(candidate_prompt_out, current_prompt)
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
            candidate_prompt=str(candidate_prompt_out),
            created_at=time.time(),
        )

        self.append_jsonl(self.loop_log, asdict(result))
        self.write_cycle_report(result, cycle_dir)
        return result

    def write_cycle_report(self, result: CycleResult, cycle_dir: Path) -> None:
        status = "本轮改进有效，candidate 已晋级为 current prompt。" if result.promoted else "本轮改进未达到阈值，candidate 未晋级。"
        text = f"""# Self Evolution Cycle {result.cycle}

## Result
- baseline_score: {result.baseline_score}
- candidate_score: {result.candidate_score}
- improved: {result.improved}
- promoted: {result.promoted}

## Files
- baseline_eval: `{result.baseline_eval}`
- candidate_eval: `{result.candidate_eval}`
- lessons: `{result.lessons}`
- candidate_prompt: `{result.candidate_prompt}`

## Conclusion
{status}
"""
        (cycle_dir / "cycle_report.md").write_text(text, encoding="utf-8")

    def run_loop(self, max_cycles: int | None = None) -> list[CycleResult]:
        if max_cycles is None:
            max_cycles = int(self.config.get("max_cycles", 3))

        results = []
        for cycle in range(1, max_cycles + 1):
            print(f"\n===== Self Evolution Cycle {cycle} =====")
            try:
                result = self.run_once(cycle)
                results.append(result)
                print(f"baseline_score : {result.baseline_score}")
                print(f"candidate_score: {result.candidate_score}")
                print(f"improved       : {result.improved}")
                print(f"promoted       : {result.promoted}")
            except Exception as exc:
                error_record = {
                    "cycle": cycle,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "created_at": time.time(),
                }
                self.append_jsonl(self.loop_log, error_record)
                print(f"Cycle {cycle} failed: {exc}")
                break

        self.write_final_report(results)
        return results

    def write_final_report(self, results: list[CycleResult]) -> None:
        lines = ["# Self Evolution Final Report", ""]
        lines.append(f"- total_cycles: {len(results)}")
        lines.append("")

        if not results:
            lines.append("没有完成任何循环。")
        else:
            best = max(results, key=lambda x: x.candidate_score)
            lines.append("## Cycles")
            lines.append("")
            for item in results:
                lines.append(
                    f"- cycle {item.cycle}: "
                    f"baseline={item.baseline_score}, "
                    f"candidate={item.candidate_score}, "
                    f"improved={item.improved}, "
                    f"promoted={item.promoted}"
                )
            lines.append("")
            lines.append("## Best")
            lines.append("")
            lines.append(f"- cycle: {best.cycle}")
            lines.append(f"- score: {best.candidate_score}")
            lines.append(f"- prompt: `{best.candidate_prompt}`")

        report_path = self.reports_dir / "final_report.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")


def init_project(config_path: str | Path) -> None:
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    prompts_dir = Path("prompts")
    prompts_dir.mkdir(exist_ok=True)

    current_prompt = prompts_dir / "current.md"
    if not current_prompt.exists():
        current_prompt.write_text(
            """# Current Coding Prompt

你是一个严谨的编程智能体。

目标：
- 正确理解题目
- 写出可运行代码
- 处理边界条件
- 输出清晰结果
- 不编造测试结果

规则：
1. 优先正确性。
2. 代码要有类型提示。
3. 失败时说明原因。
4. 不要为了复杂而复杂。
""",
            encoding="utf-8",
        )

    print(f"已初始化配置：{config_path}")
    print("请修改 config 里的 commands，让它匹配你的真实模块命令。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Self Evolution Loop Controller")
    parser.add_argument("--config", default="self_evolution_config.json")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--cycles", type=int, default=None)
    args = parser.parse_args()

    if args.init:
        init_project(args.config)
        return

    loop = SelfEvolutionLoop(args.config)
    loop.run_loop(max_cycles=args.cycles)


if __name__ == "__main__":
    main()
