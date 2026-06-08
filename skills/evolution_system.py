"""
进化系统：版本保存、评测、打分、选赢家、生成下一代提示词

用法：
    python skills/evolution_system.py

生成目录：
    evolution_lab/
    ├── candidates/
    ├── logs/
    │   ├── candidates.jsonl
    │   ├── evaluations.jsonl
    │   └── decisions.jsonl
    └── reports/
        └── evolution_report.md
"""

from __future__ import annotations

import dataclasses
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Optional


# ============================================================
# Data Models
# ============================================================

@dataclasses.dataclass
class Candidate:
    id: str
    name: str
    generation: int
    path: str
    parent_id: Optional[str]
    created_at: float
    note: str = ""


@dataclasses.dataclass
class EvaluationResult:
    candidate_id: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    runtime_ms: float
    score: float
    passed: bool
    risks: list[str]
    created_at: float


@dataclasses.dataclass
class EvolutionDecision:
    winner_id: str
    loser_ids: list[str]
    reason: str
    created_at: float


# ============================================================
# JSONL Store
# ============================================================

class JsonlStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, obj: Any) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        items = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items


# ============================================================
# Risk Auditor
# ============================================================

class RiskAuditor:
    """简单代码风险扫描器。不是安全工具，只做基础提醒。"""

    FORBIDDEN_PATTERNS = [
        r"rm\s+-rf",
        r"format\s+c:",
        r"del\s+/f\s+/s",
        r"subprocess\..*shell\s*=\s*True",
        r"os\.system\(",
        r"eval\(",
        r"exec\(",
        r"pickle\.loads",
        r"yaml\.load\(",
        r"requests\.",
        r"urllib\.request",
        r"socket\.",
    ]

    def scan_text(self, text: str) -> list[str]:
        risks = []
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                risks.append(f"matched risky pattern: {pattern}")
        return risks

    def risk_penalty(self, risks: list[str]) -> float:
        return min(50.0, len(risks) * 10.0)


# ============================================================
# Scoring
# ============================================================

class ScoreCalculator:
    """根据运行结果和风险计算分数。"""

    def calculate(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
        runtime_ms: float,
        risks: list[str],
    ) -> float:
        score = 0.0

        if returncode == 0:
            score += 60.0

        passed, failed = self._extract_pytest_counts(stdout + "\n" + stderr)

        if passed > 0:
            total = passed + failed
            if total > 0:
                score += 30.0 * (passed / total)

        if failed == 0 and passed > 0:
            score += 5.0

        if runtime_ms < 3000:
            score += 5.0
        elif runtime_ms < 10000:
            score += 2.0

        score -= min(50.0, len(risks) * 10.0)

        return max(0.0, min(100.0, score))

    def _extract_pytest_counts(self, text: str) -> tuple[int, int]:
        passed = 0
        failed = 0
        m_passed = re.search(r"(\d+)\s+passed", text)
        if m_passed:
            passed = int(m_passed.group(1))
        m_failed = re.search(r"(\d+)\s+failed", text)
        if m_failed:
            failed = int(m_failed.group(1))
        return passed, failed


# ============================================================
# Candidate Store
# ============================================================

class CandidateStore:
    def __init__(self, root: str | Path = "evolution_lab") -> None:
        self.root = Path(root)
        self.candidates_dir = self.root / "candidates"
        self.logs_dir = self.root / "logs"
        self.reports_dir = self.root / "reports"

        self.candidates_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.candidate_log = JsonlStore(self.logs_dir / "candidates.jsonl")
        self.eval_log = JsonlStore(self.logs_dir / "evaluations.jsonl")
        self.decision_log = JsonlStore(self.logs_dir / "decisions.jsonl")

    def create_candidate(
        self,
        name: str,
        content: str,
        generation: int = 0,
        parent_id: Optional[str] = None,
        note: str = "",
        suffix: str = ".py",
    ) -> Candidate:
        candidate_id = self._new_id(content)
        folder = self.candidates_dir / f"gen_{generation:04d}" / candidate_id
        folder.mkdir(parents=True, exist_ok=True)

        file_path = folder / f"{name}{suffix}"
        file_path.write_text(content, encoding="utf-8")

        candidate = Candidate(
            id=candidate_id,
            name=name,
            generation=generation,
            path=str(file_path),
            parent_id=parent_id,
            created_at=time.time(),
            note=note,
        )

        self.candidate_log.append(dataclasses.asdict(candidate))
        return candidate

    def load_candidate(self, candidate_id: str) -> Candidate:
        for item in self.candidate_log.read_all():
            if item["id"] == candidate_id:
                return Candidate(**item)
        raise KeyError(f"candidate not found: {candidate_id}")

    def read_candidate_content(self, candidate_id: str) -> str:
        candidate = self.load_candidate(candidate_id)
        return Path(candidate.path).read_text(encoding="utf-8")

    def list_candidates(self) -> list[Candidate]:
        return [Candidate(**item) for item in self.candidate_log.read_all()]

    def _new_id(self, content: str) -> str:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
        short_uuid = uuid.uuid4().hex[:6]
        return f"c_{digest}_{short_uuid}"


# ============================================================
# Evaluator
# ============================================================

class Evaluator:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.auditor = RiskAuditor()
        self.scorer = ScoreCalculator()

    def evaluate(
        self,
        candidate: Candidate,
        command: list[str],
        cwd: Optional[str | Path] = None,
    ) -> EvaluationResult:
        candidate_path = Path(candidate.path)
        content = candidate_path.read_text(encoding="utf-8")

        risks = self.auditor.scan_text(content)

        formatted_command = [
            part.replace("{file}", str(candidate_path))
            for part in command
        ]

        start = time.perf_counter()

        try:
            proc = subprocess.run(
                formatted_command,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )

            runtime_ms = (time.perf_counter() - start) * 1000

            score = self.scorer.calculate(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                runtime_ms=runtime_ms,
                risks=risks,
            )

            return EvaluationResult(
                candidate_id=candidate.id,
                command=formatted_command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                runtime_ms=runtime_ms,
                score=score,
                passed=proc.returncode == 0,
                risks=risks,
                created_at=time.time(),
            )

        except subprocess.TimeoutExpired as exc:
            runtime_ms = (time.perf_counter() - start) * 1000
            risks.append("evaluation timeout")

            return EvaluationResult(
                candidate_id=candidate.id,
                command=formatted_command,
                returncode=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "timeout",
                runtime_ms=runtime_ms,
                score=0.0,
                passed=False,
                risks=risks,
                created_at=time.time(),
            )


# ============================================================
# Evolution Engine
# ============================================================

class EvolutionEngine:
    """进化系统核心：创建候选、评测、选择、生成下一轮提示。"""

    def __init__(self, root: str | Path = "evolution_lab") -> None:
        self.store = CandidateStore(root)
        self.evaluator = Evaluator()

    def seed(
        self,
        name: str,
        content: str,
        note: str = "seed version",
    ) -> Candidate:
        return self.store.create_candidate(
            name=name,
            content=content,
            generation=0,
            parent_id=None,
            note=note,
        )

    def mutate_manual(
        self,
        parent_id: str,
        new_content: str,
        note: str = "manual mutation",
    ) -> Candidate:
        parent = self.store.load_candidate(parent_id)
        return self.store.create_candidate(
            name=parent.name,
            content=new_content,
            generation=parent.generation + 1,
            parent_id=parent.id,
            note=note,
        )

    def evaluate_candidate(
        self,
        candidate_id: str,
        command: list[str],
        cwd: Optional[str | Path] = None,
    ) -> EvaluationResult:
        candidate = self.store.load_candidate(candidate_id)
        result = self.evaluator.evaluate(candidate, command, cwd)
        self.store.eval_log.append(dataclasses.asdict(result))
        return result

    def tournament(self, candidate_ids: list[str]) -> EvolutionDecision:
        evaluations = self.store.eval_log.read_all()

        latest_by_id: dict[str, dict[str, Any]] = {}

        for item in evaluations:
            cid = item["candidate_id"]
            if cid in candidate_ids:
                old = latest_by_id.get(cid)
                if old is None or item["created_at"] > old["created_at"]:
                    latest_by_id[cid] = item

        if not latest_by_id:
            raise ValueError("no evaluation results found for candidates")

        ranked = sorted(
            latest_by_id.values(),
            key=lambda x: x["score"],
            reverse=True,
        )

        winner = ranked[0]
        loser_ids = [item["candidate_id"] for item in ranked[1:]]

        reason = (
            f"winner={winner['candidate_id']} score={winner['score']:.2f}; "
            f"selected by latest evaluation score"
        )

        decision = EvolutionDecision(
            winner_id=winner["candidate_id"],
            loser_ids=loser_ids,
            reason=reason,
            created_at=time.time(),
        )

        self.store.decision_log.append(dataclasses.asdict(decision))
        return decision

    def diff(self, old_id: str, new_id: str) -> str:
        old_text = self.store.read_candidate_content(old_id).splitlines()
        new_text = self.store.read_candidate_content(new_id).splitlines()
        return "\n".join(
            difflib.unified_diff(
                old_text, new_text,
                fromfile=old_id, tofile=new_id, lineterm="",
            )
        )

    def generate_next_prompt(self, winner_id: str) -> str:
        winner = self.store.load_candidate(winner_id)
        content = self.store.read_candidate_content(winner_id)

        prompt = f"""你现在基于上一代代码继续进化。

上一代候选：
- id: {winner.id}
- generation: {winner.generation}
- path: {winner.path}
- note: {winner.note}

目标：
在保持公共 API 兼容的前提下，让代码更稳定、更可测试、更适合长期运行。

进化要求：
1. 不要重写整个文件。
2. 优先修复真实问题。
3. 保持类型提示。
4. 增加边界处理。
5. 增加必要注释。
6. 不引入第三方依赖。
7. 不访问网络。
8. 不删除用户文件。
9. 修改后必须运行测试。
10. 不要编造测试结果。

请输出：
1. 修改后的完整代码
2. 修改点列表
3. 测试命令
4. 真实测试结果
5. 仍然存在的限制

上一代代码如下：

```python
{content}
```"""

        return prompt

    def export_report(self) -> str:
        candidates = self.store.candidate_log.read_all()
        evaluations = self.store.eval_log.read_all()
        decisions = self.store.decision_log.read_all()

        lines = []
        lines.append("# Evolution System Report")
        lines.append("")
        lines.append(f"候选版本数量：{len(candidates)}")
        lines.append(f"评测记录数量：{len(evaluations)}")
        lines.append(f"选择记录数量：{len(decisions)}")
        lines.append("")

        lines.append("## Candidates")
        for item in candidates:
            lines.append(
                f"- {item['id']} | gen={item['generation']} | "
                f"parent={item['parent_id']} | path={item['path']} | note={item['note']}"
            )

        lines.append("")
        lines.append("## Evaluations")
        for item in evaluations:
            lines.append(
                f"- {item['candidate_id']} | score={item['score']:.2f} | "
                f"passed={item['passed']} | runtime={item['runtime_ms']:.2f}ms | "
                f"risks={len(item['risks'])}"
            )

        lines.append("")
        lines.append("## Decisions")
        for item in decisions:
            lines.append(
                f"- winner={item['winner_id']} | losers={item['loser_ids']} | "
                f"reason={item['reason']}"
            )

        report = "\n".join(lines)

        report_path = self.store.reports_dir / "evolution_report.md"
        report_path.write_text(report, encoding="utf-8")

        return report


# ============================================================
# Demo
# ============================================================

DEMO_CODE_V1 = """
def add(a: int, b: int) -> int:
    return a + b
""".strip()

DEMO_CODE_V2 = '''
def add(a: int, b: int) -> int:
    """Return sum of two integers."""
    if not isinstance(a, int):
        raise TypeError("a must be int")
    if not isinstance(b, int):
        raise TypeError("b must be int")
    return a + b
'''.strip()


def main() -> None:
    engine = EvolutionEngine(root="evolution_lab")

    c1 = engine.seed(
        name="demo_add",
        content=DEMO_CODE_V1,
        note="基础版本",
    )

    c2 = engine.mutate_manual(
        parent_id=c1.id,
        new_content=DEMO_CODE_V2,
        note="增加类型校验和 docstring",
    )

    r1 = engine.evaluate_candidate(
        c1.id,
        command=["python", "-m", "py_compile", "{file}"],
    )

    r2 = engine.evaluate_candidate(
        c2.id,
        command=["python", "-m", "py_compile", "{file}"],
    )

    decision = engine.tournament([c1.id, c2.id])

    print("Candidate 1:", c1.id, "score:", r1.score)
    print("Candidate 2:", c2.id, "score:", r2.score)
    print("Winner:", decision.winner_id)
    print()
    print(engine.export_report())
    print()
    print("下一代进化提示词：")
    print(engine.generate_next_prompt(decision.winner_id))


if __name__ == "__main__":
    main()
