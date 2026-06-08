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
