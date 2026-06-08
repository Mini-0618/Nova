"""
Self Evolution Loop
跑任务 -> 评估 -> 分析失败 -> 生成改进 -> 再评估 -> 分数提升则晋级

用法：
    python skills/self_evolution_loop.py --init
    python skills/self_evolution_loop.py --cycles 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import sys as _sys
_root = Path(__file__).parent.parent
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))


DEFAULT_CONFIG = {
    "workspace": "self_evolution_runs",
    "current_prompt": "prompts/current.md",
    "candidate_prompt": "prompts/candidate.md",
    "min_improve": 0.01,
    "max_cycles": 3,
    "timeout_sec": 600,
    "model": "deepseek-chat",
    "score_keys": ["score", "accuracy", "pass_rate", "pass_rate"],
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

    def _log_step(self, name: str, command: str, returncode: int,
                  stdout: str, stderr: str, runtime_sec: float, ok: bool) -> None:
        result = StepResult(
            name=name, command=command, returncode=returncode,
            stdout=stdout[-10000:], stderr=stderr[-10000:],
            runtime_sec=runtime_sec, ok=ok,
        )
        self.append_jsonl(self.step_log, asdict(result))

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

    async def _run_eval(self, model: str) -> tuple[float, str]:
        """Run eval using run_eval.py directly. Returns (pass_rate, report_path)."""
        from data.eval.run_eval import load_tasks, run_task_with_loop, build_report, REPORTS_DIR

        tasks = load_tasks()
        results = []
        for task in tasks:
            result = await run_task_with_loop(task, model=model)
            results.append(result)

        report = build_report(results)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORTS_DIR / f"evolution-{time.strftime('%Y%m%d-%H%M%S')}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)

        return report.pass_rate, str(report_path)

    async def _extract_lessons(self, report_path: str, model: str) -> str:
        """Extract lessons from eval report using auto_lessons.py."""
        from data.eval.auto_lessons import extract_lessons_from_report, LESSONS_FILE
        await extract_lessons_from_report(report_path, model=model)
        return str(LESSONS_FILE)

    def _improve_prompt(self, current_prompt: Path, lessons_file: str,
                        candidate_prompt_out: Path) -> None:
        """Generate improved prompt using evolution_system."""
        from skills.evolution_system import EvolutionEngine

        engine = EvolutionEngine(root="evolution_lab")

        # Read current prompt content
        if current_prompt.exists():
            content = current_prompt.read_text(encoding="utf-8")
        else:
            content = "# Default prompt\nYou are a coding agent."

        # Seed and generate next prompt
        candidate = engine.seed(name="current_prompt", content=content, note="current version")
        next_prompt_text = engine.generate_next_prompt(candidate.id)

        # Write the improved prompt
        candidate_prompt_out.parent.mkdir(parents=True, exist_ok=True)
        candidate_prompt_out.write_text(next_prompt_text, encoding="utf-8")

    async def run_once(self, cycle: int) -> CycleResult:
        cycle_dir = self.cycles_dir / f"cycle_{cycle:04d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        model = self.config.get("model", "deepseek-chat")
        current_prompt = Path(self.config["current_prompt"])
        candidate_prompt_out = cycle_dir / "candidate_prompt.md"
        lessons_file = str(cycle_dir / "lessons.json")

        # 1. Run eval on current prompt
        print(f"  [1/5] Running baseline eval...")
        start = time.perf_counter()
        baseline_score, baseline_report = await self._run_eval(model)
        self._log_step("baseline.eval", "run_eval", 0,
                       f"pass_rate={baseline_score}", "", time.perf_counter() - start, True)

        # 2. Extract lessons from failures
        print(f"  [2/5] Extracting lessons from failures...")
        start = time.perf_counter()
        lessons_path = await self._extract_lessons(baseline_report, model)
        self._log_step("extract_lessons", "auto_lessons", 0,
                       f"lessons={lessons_path}", "", time.perf_counter() - start, True)

        # 3. Improve prompt based on lessons
        print(f"  [3/5] Generating improved prompt...")
        start = time.perf_counter()
        self._improve_prompt(current_prompt, lessons_path, candidate_prompt_out)
        self._log_step("improve_prompt", "evolution_system", 0,
                       "prompt generated", "", time.perf_counter() - start, True)

        # 4. Swap to candidate prompt and re-eval
        print(f"  [4/5] Running candidate eval...")
        # Temporarily swap prompt
        original_backup = None
        if current_prompt.exists():
            original_backup = cycle_dir / "original_prompt_backup.md"
            shutil.copy2(current_prompt, original_backup)
        shutil.copy2(candidate_prompt_out, current_prompt)

        start = time.perf_counter()
        candidate_score, candidate_report = await self._run_eval(model)
        self._log_step("candidate.eval", "run_eval", 0,
                       f"pass_rate={candidate_score}", "", time.perf_counter() - start, True)

        # 5. Decide: promote or rollback
        min_improve = float(self.config.get("min_improve", 0.01))
        improved = candidate_score > baseline_score + min_improve
        promoted = False

        if improved:
            print(f"  [5/5] Improved! Promoting candidate prompt.")
            promoted = True
            # Keep the candidate prompt as current
        else:
            print(f"  [5/5] No improvement. Rolling back.")
            if original_backup and original_backup.exists():
                shutil.copy2(original_backup, current_prompt)

        result = CycleResult(
            cycle=cycle,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            improved=improved,
            promoted=promoted,
            baseline_eval=baseline_report,
            candidate_eval=candidate_report,
            lessons=lessons_path,
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

    async def run_loop(self, max_cycles: int | None = None) -> list[CycleResult]:
        if max_cycles is None:
            max_cycles = int(self.config.get("max_cycles", 3))

        results = []
        for cycle in range(1, max_cycles + 1):
            print(f"\n===== Self Evolution Cycle {cycle}/{max_cycles} =====")
            try:
                result = await self.run_once(cycle)
                results.append(result)
                print(f"  baseline_score : {result.baseline_score}")
                print(f"  candidate_score: {result.candidate_score}")
                print(f"  improved       : {result.improved}")
                print(f"  promoted       : {result.promoted}")
            except Exception as exc:
                error_record = {
                    "cycle": cycle,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "created_at": time.time(),
                }
                self.append_jsonl(self.loop_log, error_record)
                print(f"  Cycle {cycle} failed: {exc}")
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


async def _async_main() -> None:
    parser = argparse.ArgumentParser(description="Self Evolution Loop Controller")
    parser.add_argument("--config", default="self_evolution_config.json")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--cycles", type=int, default=None)
    args = parser.parse_args()

    if args.init:
        init_project(args.config)
        return

    loop = SelfEvolutionLoop(args.config)
    await loop.run_loop(max_cycles=args.cycles)


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
