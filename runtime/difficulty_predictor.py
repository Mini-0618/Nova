"""
Task Difficulty Predictor
Estimates how many iterations a task will need based on:
- Task description keywords
- Category and declared difficulty
- Historical performance data

Nova's Innovation #2
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"
HISTORY_FILE = KNOWLEDGE_DIR / "task_history.json"

# Keyword-based difficulty signals
HARD_SIGNALS = [
    "circular", "race condition", "thread", "atomic", "refactor across",
    "multiple files", "integration", "concurrent", "deadlock", "async",
    "complex", "reduce complexity", "full pipeline", "comprehensive",
]

MEDIUM_SIGNALS = [
    "json", "parse", "filter", "search", "replace", "config", "argument",
    "parametrize", "edge case", "type hint", "extract", "merge",
]

EASY_SIGNALS = [
    "create a file", "write the", "append", "read and", "copy",
    "list", "run a command", "check exit", "hello world",
]

# Category base difficulty multipliers
CATEGORY_MULTIPLIERS = {
    "file_io": 1.0,
    "bugfix": 1.3,
    "cli": 1.1,
    "refactor": 1.4,
    "test_writing": 1.2,
    "multi_file": 1.5,
    "agent_loop": 1.6,
    "self_improve": 1.3,
}

# Difficulty level to base iteration estimate
DIFFICULTY_BASE = {
    "easy": 3,
    "medium": 5,
    "hard": 8,
}


class DifficultyPredictor:
    """Predicts task difficulty and resource requirements."""

    def __init__(self):
        self.history = self._load_history()

    def _load_history(self) -> Dict:
        """Load historical task performance data."""
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"tasks": {}, "patterns": {}}

    def save_history(self):
        """Save updated history."""
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_FILE.write_text(
            json.dumps(self.history, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def predict(self, task_description: str, category: str = "",
                declared_difficulty: str = "medium") -> Dict:
        """
        Predict task difficulty and resource requirements.

        Returns:
            {
                "estimated_iterations": int,
                "estimated_tokens": int,
                "confidence": float (0-1),
                "difficulty_score": float (0-10),
                "signals": list[str],
                "recommended_token_budget": int,
            }
        """
        desc_lower = task_description.lower()
        signals = []
        score = 0.0

        # Base from declared difficulty
        base_iters = DIFFICULTY_BASE.get(declared_difficulty, 5)
        score += {"easy": 2, "medium": 5, "hard": 8}.get(declared_difficulty, 5)

        # Keyword analysis
        for kw in HARD_SIGNALS:
            if kw in desc_lower:
                signals.append(f"hard:{kw}")
                score += 1.5

        for kw in MEDIUM_SIGNALS:
            if kw in desc_lower:
                signals.append(f"medium:{kw}")
                score += 0.5

        for kw in EASY_SIGNALS:
            if kw in desc_lower:
                signals.append(f"easy:{kw}")
                score -= 0.5

        # Category multiplier
        cat_mult = CATEGORY_MULTIPLIERS.get(category, 1.0)
        score *= cat_mult

        # Task length signal (longer descriptions = more complex)
        word_count = len(task_description.split())
        if word_count > 50:
            score += 1.0
            signals.append("long_description")
        elif word_count < 15:
            score -= 0.5
            signals.append("short_description")

        # Number of files involved
        file_mentions = len(re.findall(r'\b\w+\.\w+\b', task_description))
        if file_mentions > 3:
            score += 1.0
            signals.append(f"multi_file({file_mentions})")

        # Setup files signal
        if "setup_files" in task_description or "project/" in task_description:
            score += 0.5
            signals.append("has_setup_files")

        # Clamp score
        score = max(1.0, min(10.0, score))

        # Estimate iterations based on score
        estimated_iters = max(2, int(score * 1.2))

        # Estimate tokens (each iteration ~2k input + 1k output)
        estimated_tokens = estimated_iters * 3000

        # Historical adjustment
        task_key = self._make_task_key(task_description)
        if task_key in self.history.get("tasks", {}):
            hist = self.history["tasks"][task_key]
            if "actual_iterations" in hist:
                # Blend prediction with history
                actual = hist["actual_iterations"]
                estimated_iters = int(estimated_iters * 0.4 + actual * 0.6)
                estimated_tokens = estimated_iters * 3000
                signals.append(f"history_adjusted(from={base_iters},actual={actual})")

        # Confidence: higher if we have history, lower for unusual patterns
        confidence = 0.6
        if task_key in self.history.get("tasks", {}):
            confidence = 0.85
        if len(signals) > 5:
            confidence -= 0.1  # Too many signals = uncertain

        # Recommended budget: 2x estimate for safety
        recommended_budget = estimated_tokens * 2

        return {
            "estimated_iterations": estimated_iters,
            "estimated_tokens": estimated_tokens,
            "confidence": round(confidence, 2),
            "difficulty_score": round(score, 1),
            "signals": signals,
            "recommended_token_budget": recommended_budget,
        }

    def record_outcome(self, task_description: str, category: str,
                       actual_iterations: int, actual_tokens: int,
                       passed: bool, duration_s: float):
        """Record actual task outcome for future predictions."""
        task_key = self._make_task_key(task_description)
        if "tasks" not in self.history:
            self.history["tasks"] = {}
        self.history["tasks"][task_key] = {
            "category": category,
            "actual_iterations": actual_iterations,
            "actual_tokens": actual_tokens,
            "passed": passed,
            "duration_s": duration_s,
            "description_prefix": task_description[:100],
        }
        self.save_history()

    def _make_task_key(self, description: str) -> str:
        """Create a stable key for a task description."""
        # Normalize and hash
        normalized = re.sub(r'\s+', ' ', description.strip().lower())
        # Use first 80 chars as key (fuzzy match)
        return normalized[:80]


# Singleton
_predictor: Optional[DifficultyPredictor] = None

def get_predictor() -> DifficultyPredictor:
    global _predictor
    if _predictor is None:
        _predictor = DifficultyPredictor()
    return _predictor
