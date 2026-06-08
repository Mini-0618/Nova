"""
多文件项目生成器：自动创建 20+ 文件的自我进化系统工程

用法：
    python skills/make_self_evolve_project.py

生成目录：
    self_evolve_project/
    ├── configs/default.json
    ├── prompts/current.md
    ├── scripts/ (4 个脚本)
    ├── src/self_evolve/ (12 个模块)
    ├── tests/ (5 个测试)
    ├── README.md, pyproject.toml, run.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path


PROJECT = "self_evolve_project"


FILES: dict[str, str] = {
    ".gitignore": """
__pycache__/
*.pyc
.pytest_cache/
.venv/
self_evolution_runs/
dist/
build/
*.egg-info/
""",

    "pyproject.toml": """
[project]
name = "self-evolve-project"
version = "0.1.0"
description = "A multi-file self evolution loop for coding agents"
requires-python = ">=3.10"
dependencies = []

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
""",

    "README.md": """
# Self Evolve Project

多文件版自我进化主控系统。

核心循环：

    执行任务 -> 评估结果 -> 分析失败 -> 改进 Prompt -> 再执行 -> 对比分数 -> 晋级或丢弃

## 初始化

    python run.py init

## 跑一轮 demo

    python run.py cycle --config configs/default.json

## 跑多轮

    python run.py loop --config configs/default.json --cycles 3
""",

    "run.py": """
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from self_evolve.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
""",

    "configs/default.json": """
{
    "workspace": "self_evolution_runs",
    "current_prompt": "prompts/current.md",
    "min_improve": 0.01,
    "timeout_sec": 120,
    "score_keys": ["score", "accuracy", "pass_rate"],
    "commands": {
        "run_task": "{python} scripts/fake_task.py --prompt {prompt} --out {task_out}",
        "eval": "{python} scripts/fake_eval.py --input {task_out} --out {eval_out}",
        "analyze_failure": "{python} scripts/fake_analyzer.py --eval {eval_out} --out {lessons_out}",
        "improve_prompt": "{python} scripts/fake_improver.py --prompt {prompt} --lessons {lessons_out} --out {candidate_prompt}"
    }
}
""",

    "prompts/current.md": """
# Current Coding Prompt

你是一个严谨的编程智能体。

规则：
1. 优先正确性。
2. 写出可运行代码。
3. 处理边界条件。
4. 不编造测试结果。
5. 失败时说明原因。
""",

    "src/self_evolve/__init__.py": """
from self_evolve.loop import SelfEvolutionLoop

__all__ = ["SelfEvolutionLoop"]
""",

    "src/self_evolve/models.py": """
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


@dataclass
class FailureLesson:
    category: str
    message: str
    suggestion: str


@dataclass
class ScoreInfo:
    score: float
    raw: dict[str, Any]
""",

    "src/self_evolve/store.py": """
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, data: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []

        rows: list[dict[str, Any]] = []

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))

        return rows
""",

    "src/self_evolve/config.py": """
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")

    return json.loads(p.read_text(encoding="utf-8"))


def ensure_dirs(config: dict[str, Any]) -> dict[str, Path]:
    workspace = Path(config["workspace"])
    cycles = workspace / "cycles"
    logs = workspace / "logs"
    reports = workspace / "reports"

    for path in (workspace, cycles, logs, reports):
        path.mkdir(parents=True, exist_ok=True)

    return {
        "workspace": workspace,
        "cycles": cycles,
        "logs": logs,
        "reports": reports,
    }
""",

    "src/self_evolve/runner.py": """
from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path

from self_evolve.models import StepResult


class CommandRunner:
    def __init__(self, timeout_sec: float = 120) -> None:
        self.timeout_sec = timeout_sec

    def run(self, name: str, command: str, cwd: str | Path | None = None) -> StepResult:
        start = time.perf_counter()

        try:
            # On Windows, use shell=True with the command as string
            # to avoid shlex.split mangling paths
            import sys as _sys
            if _sys.platform == "win32":
                cmd = command
                use_shell = True
            else:
                cmd = shlex.split(command)
                use_shell = False

            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                shell=use_shell,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_sec,
            )

            runtime = time.perf_counter() - start

            return StepResult(
                name=name,
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout[-10000:],
                stderr=proc.stderr[-10000:],
                runtime_sec=runtime,
                ok=proc.returncode == 0,
            )

        except subprocess.TimeoutExpired as exc:
            runtime = time.perf_counter() - start

            return StepResult(
                name=name,
                command=command,
                returncode=124,
                stdout=str(exc.stdout or "")[-10000:],
                stderr=str(exc.stderr or "timeout")[-10000:],
                runtime_sec=runtime,
                ok=False,
            )
""",

    "src/self_evolve/scoring.py": """
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from self_evolve.models import ScoreInfo


class ScoreExtractor:
    def __init__(self, score_keys: list[str] | None = None) -> None:
        self.score_keys = score_keys or ["score", "accuracy", "pass_rate"]

    def extract_from_file(self, path: str | Path) -> ScoreInfo:
        p = Path(path)
        text = p.read_text(encoding="utf-8", errors="replace")

        try:
            data = json.loads(text)
            score = self._extract_from_json(data)
            if score is not None:
                return ScoreInfo(score=float(score), raw=data)
        except json.JSONDecodeError:
            data = {"text": text}

        score = self._extract_from_text(text)

        if score is None:
            raise ValueError(f"cannot extract score from: {p}")

        return ScoreInfo(score=float(score), raw=data)

    def _extract_from_json(self, data: Any) -> float | None:
        if isinstance(data, dict):
            for key in self.score_keys:
                value = data.get(key)
                if isinstance(value, (int, float)):
                    return float(value)

            for value in data.values():
                found = self._extract_from_json(value)
                if found is not None:
                    return found

        if isinstance(data, list):
            for item in data:
                found = self._extract_from_json(item)
                if found is not None:
                    return found

        return None

    def _extract_from_text(self, text: str) -> float | None:
        patterns = [
            r"score\\s*[:=]\\s*([0-9]+(?:\\.[0-9]+)?)",
            r"accuracy\\s*[:=]\\s*([0-9]+(?:\\.[0-9]+)?)",
            r"pass_rate\\s*[:=]\\s*([0-9]+(?:\\.[0-9]+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))

        return None
""",

    "src/self_evolve/prompts.py": """
from __future__ import annotations

import shutil
import time
from pathlib import Path


class PromptManager:
    def __init__(self, current_prompt: str | Path) -> None:
        self.current_prompt = Path(current_prompt)

    def promote(self, candidate_prompt: str | Path) -> None:
        candidate = Path(candidate_prompt)

        if not candidate.exists():
            raise FileNotFoundError(str(candidate))

        self.current_prompt.parent.mkdir(parents=True, exist_ok=True)

        if self.current_prompt.exists():
            backup = self.current_prompt.with_suffix(
                self.current_prompt.suffix + f".bak_{int(time.time())}"
            )
            shutil.copy2(self.current_prompt, backup)

        shutil.copy2(candidate, self.current_prompt)
""",

    "src/self_evolve/analyzer.py": """
from __future__ import annotations

import json
from pathlib import Path

from self_evolve.models import FailureLesson


class FailureAnalyzer:
    def analyze_eval_file(self, eval_path: str | Path) -> list[FailureLesson]:
        p = Path(eval_path)
        text = p.read_text(encoding="utf-8", errors="replace")

        lessons: list[FailureLesson] = []

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"raw": text}

        failed = int(data.get("failed", 0)) if isinstance(data, dict) else 0
        score = float(data.get("score", 0)) if isinstance(data, dict) else 0

        if failed > 0:
            lessons.append(
                FailureLesson(
                    category="test_failure",
                    message=f"failed cases: {failed}",
                    suggestion="Next prompt must handle failure cases and edge conditions first.",
                )
            )

        if score < 0.8:
            lessons.append(
                FailureLesson(
                    category="low_score",
                    message=f"low score: {score}",
                    suggestion="Strengthen requirement restatement, edge handling, error handling, and test generation.",
                )
            )

        if not lessons:
            lessons.append(
                FailureLesson(
                    category="stable",
                    message="no obvious failures",
                    suggestion="Keep current strategy, only small optimizations.",
                )
            )

        return lessons
""",

    "src/self_evolve/improver.py": """
from __future__ import annotations

import json
from pathlib import Path


class PromptImprover:
    def improve(self, prompt_path: str | Path, lessons_path: str | Path, out_path: str | Path) -> None:
        prompt = Path(prompt_path).read_text(encoding="utf-8")
        lessons_text = Path(lessons_path).read_text(encoding="utf-8")

        try:
            lessons = json.loads(lessons_text)
        except json.JSONDecodeError:
            lessons = [{"suggestion": lessons_text}]

        additions = []
        additions.append("")
        additions.append("## Evolution Lessons")
        additions.append("")
        additions.append("Next round must absorb these lessons:")

        for item in lessons:
            suggestion = item.get("suggestion", str(item))
            additions.append(f"- {suggestion}")

        additions.append("")
        additions.append("New rules:")
        additions.append("1. Handle failure cases first, then optimize style.")
        additions.append("2. Check edge conditions before outputting code.")
        additions.append("3. Never fabricate test results.")
        additions.append("4. If uncertain, implement conservatively.")

        out = prompt.rstrip() + "\\n" + "\\n".join(additions) + "\\n"

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")
""",

    "src/self_evolve/reporting.py": """
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
    Path(reports_dir, "final_report.md").write_text("\\n".join(lines), encoding="utf-8")
""",

    "src/self_evolve/loop.py": """
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
                f"step failed: {step.name}\\n"
                f"command: {step.command}\\n"
                f"returncode: {step.returncode}\\n"
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
""",

    "src/self_evolve/cli.py": """
from __future__ import annotations

import argparse

from self_evolve.loop import SelfEvolutionLoop


def main() -> int:
    parser = argparse.ArgumentParser(description="Self Evolution Multi-file System")

    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")

    p_cycle = sub.add_parser("cycle")
    p_cycle.add_argument("--config", default="configs/default.json")

    p_loop = sub.add_parser("loop")
    p_loop.add_argument("--config", default="configs/default.json")
    p_loop.add_argument("--cycles", type=int, default=3)

    args = parser.parse_args()

    if args.cmd == "init":
        print("project already initialized by generator")
        return 0

    if args.cmd == "cycle":
        loop = SelfEvolutionLoop(args.config)
        loop.run_once(1)
        return 0

    if args.cmd == "loop":
        loop = SelfEvolutionLoop(args.config)
        loop.run_loop(args.cycles)
        return 0

    return 2
""",

    "src/self_evolve/__main__.py": """
from self_evolve.cli import main

raise SystemExit(main())
""",

    "scripts/fake_task.py": """
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    prompt = Path(args.prompt).read_text(encoding="utf-8")

    bonus = 0
    if "Evolution Lessons" in prompt:
        bonus += 1
    if "edge" in prompt.lower() or "boundary" in prompt.lower():
        bonus += 1
    if "test" in prompt.lower():
        bonus += 1

    total = 10
    passed = min(total, 7 + bonus)
    failed = total - passed

    rows = []
    for i in range(total):
        rows.append(
            {
                "task_id": i + 1,
                "passed": i < passed,
                "error": "" if i < passed else "boundary case failed",
            }
        )

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)

    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\\n")


if __name__ == "__main__":
    main()
""",

    "scripts/fake_eval.py": """
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    passed = 0
    failed = 0

    with Path(args.input).open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("passed"):
                passed += 1
            else:
                failed += 1

    total = passed + failed
    score = passed / total if total else 0.0

    data = {
        "score": score,
        "passed": passed,
        "failed": failed,
        "total": total,
    }

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
""",

    "scripts/fake_analyzer.py": """
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.eval).read_text(encoding="utf-8"))

    lessons = []

    if data.get("failed", 0) > 0:
        lessons.append(
            {
                "category": "failure",
                "message": f"failed cases: {data['failed']}",
                "suggestion": "Strengthen edge conditions, error handling, and test coverage.",
            }
        )
    else:
        lessons.append(
            {
                "category": "stable",
                "message": "no failures",
                "suggestion": "Keep strategy, small optimizations.",
            }
        )

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
""",

    "scripts/fake_improver.py": """
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--lessons", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    prompt = Path(args.prompt).read_text(encoding="utf-8")
    lessons = json.loads(Path(args.lessons).read_text(encoding="utf-8"))

    lines = []
    lines.append(prompt.rstrip())
    lines.append("")
    lines.append("## Evolution Lessons")
    lines.append("")

    for lesson in lessons:
        lines.append(f"- {lesson.get('suggestion', '')}")

    lines.append("")
    lines.append("New requirements:")
    lines.append("1. Pay more attention to edge conditions.")
    lines.append("2. Pay more attention to test coverage.")
    lines.append("3. Pay more attention to error handling.")

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
""",

    "tests/test_scoring.py": """
from pathlib import Path

from self_evolve.scoring import ScoreExtractor


def test_extract_score_from_json(tmp_path: Path) -> None:
    p = tmp_path / "eval.json"
    p.write_text('{"score": 0.75}', encoding="utf-8")

    info = ScoreExtractor().extract_from_file(p)

    assert info.score == 0.75
""",

    "tests/test_store.py": """
from self_evolve.store import JsonlStore


def test_jsonl_store(tmp_path) -> None:
    store = JsonlStore(tmp_path / "x.jsonl")
    store.append({"a": 1})
    store.append({"b": 2})

    rows = store.read_all()

    assert rows == [{"a": 1}, {"b": 2}]
""",

    "tests/test_analyzer.py": """
import json

from self_evolve.analyzer import FailureAnalyzer


def test_failure_analyzer(tmp_path) -> None:
    p = tmp_path / "eval.json"
    p.write_text(json.dumps({"score": 0.5, "failed": 2}), encoding="utf-8")

    lessons = FailureAnalyzer().analyze_eval_file(p)

    assert lessons
    assert lessons[0].category == "test_failure"
""",

    "tests/test_improver.py": """
import json

from self_evolve.improver import PromptImprover


def test_prompt_improver(tmp_path) -> None:
    prompt = tmp_path / "prompt.md"
    lessons = tmp_path / "lessons.json"
    out = tmp_path / "out.md"

    prompt.write_text("hello", encoding="utf-8")
    lessons.write_text(json.dumps([{"suggestion": "fix boundary"}]), encoding="utf-8")

    PromptImprover().improve(prompt, lessons, out)

    assert "fix boundary" in out.read_text(encoding="utf-8")
""",

    "tests/test_models.py": """
from self_evolve.models import CycleResult


def test_cycle_result_model() -> None:
    item = CycleResult(
        cycle=1,
        baseline_score=0.7,
        candidate_score=0.8,
        improved=True,
        promoted=True,
        baseline_eval="a.json",
        candidate_eval="b.json",
        lessons="lessons.json",
        candidate_prompt="prompt.md",
        created_at=1.0,
    )

    assert item.improved is True
""",
}


def write_project() -> None:
    root = Path(PROJECT)

    for relative_path, content in FILES.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    print(f"已生成项目：{root.resolve()}")
    print()
    print("下一步：")
    print(f"cd {PROJECT}")
    print("python run.py init")
    print("python run.py cycle --config configs/default.json")
    print("python run.py loop --config configs/default.json --cycles 3")


if __name__ == "__main__":
    write_project()
