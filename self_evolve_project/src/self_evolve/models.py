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
