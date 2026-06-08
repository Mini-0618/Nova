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
            r"score\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"accuracy\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"pass_rate\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))

        return None
