"""
Cross-Task Learning Module
Injects recently learned patterns into the system prompt
so lessons from Task A help with Task B.

Nova's Innovation #4
"""

import json
from pathlib import Path
from typing import List, Dict, Optional

KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"
LESSONS_FILE = Path(__file__).parent.parent / "data" / "eval" / "lessons.json"
FAILURE_PATTERNS_FILE = KNOWLEDGE_DIR / "failure_patterns.json"
REFLECTIONS_DIR = KNOWLEDGE_DIR / "reflections"


class CrossTaskLearner:
    """Manages cross-task learning by injecting patterns into prompts."""

    def __init__(self):
        self.lessons = self._load_lessons()
        self.failure_patterns = self._load_failure_patterns()

    def _load_lessons(self) -> List[Dict]:
        """Load lessons from eval runs."""
        if LESSONS_FILE.exists():
            try:
                return json.loads(LESSONS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _load_failure_patterns(self) -> List[Dict]:
        """Load failure patterns library."""
        if FAILURE_PATTERNS_FILE.exists():
            try:
                data = json.loads(FAILURE_PATTERNS_FILE.read_text(encoding="utf-8"))
                return data.get("patterns", [])
            except Exception:
                pass
        return []

    def get_relevant_patterns(self, task_description: str, category: str = "",
                              max_patterns: int = 5) -> List[Dict]:
        """Find patterns relevant to the current task."""
        desc_lower = task_description.lower()
        relevant = []

        # Match failure patterns by category and keywords
        for pattern in self.failure_patterns:
            score = 0
            if pattern.get("category") == category:
                score += 2
            # Check if task description matches pattern examples
            for example in pattern.get("examples", []):
                if example.lower() in desc_lower:
                    score += 3
            # Check symptom keywords
            for keyword in pattern.get("symptom", "").lower().split():
                if keyword in desc_lower and len(keyword) > 3:
                    score += 1
            if score > 0:
                relevant.append((score, pattern))

        # Match lessons from eval runs
        for lesson in self.lessons:
            score = 0
            if lesson.get("category") == category:
                score += 1
            pattern_text = lesson.get("pattern", "").lower()
            for word in pattern_text.split():
                if word in desc_lower and len(word) > 4:
                    score += 1
            if score > 0:
                relevant.append((score, {
                    "name": lesson.get("pattern", "")[:50],
                    "fix_strategy": lesson.get("fix", ""),
                    "source": "eval_lesson",
                }))

        # Sort by relevance, return top N
        relevant.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in relevant[:max_patterns]]

    def get_learning_injection(self, task_description: str, category: str = "") -> str:
        """
        Generate a text block to inject into the system prompt.
        Contains relevant patterns and lessons for the current task.
        """
        patterns = self.get_relevant_patterns(task_description, category)

        if not patterns:
            return ""

        lines = [
            "",
            "## Learned Patterns (from previous tasks)",
            "Apply these lessons to avoid known failure modes:",
            "",
        ]

        for i, p in enumerate(patterns, 1):
            name = p.get("name", "Unknown pattern")
            fix = p.get("fix_strategy", p.get("fix", ""))
            if fix:
                lines.append(f"{i}. **{name}**: {fix}")
            else:
                lines.append(f"{i}. **{name}**")

        lines.append("")
        lines.append("Avoid these patterns. Act decisively. Don't re-read files you already have in context.")

        return "\n".join(lines)

    def record_learning(self, task_id: str, category: str,
                        pattern: str, fix: str, confidence: float = 0.7):
        """Record a new learning from a task outcome."""
        new_lesson = {
            "id": f"auto-{task_id}",
            "pattern": pattern,
            "fix": fix,
            "category": category,
            "source_task": task_id,
            "confidence": confidence,
            "times_applied": 0,
            "times_successful": 0,
        }

        self.lessons.append(new_lesson)

        # Save back
        LESSONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        LESSONS_FILE.write_text(
            json.dumps(self.lessons, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def get_recent_reflection_context(self, limit: int = 3) -> str:
        """Get recent reflections to inject as context."""
        if not REFLECTIONS_DIR.exists():
            return ""

        files = sorted(REFLECTIONS_DIR.glob("*.md"), reverse=True)[:limit]
        if not files:
            return ""

        lines = ["", "## Recent Task Reflections"]
        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                # Extract just the "What I Learned" section
                if "## What I Learned" in content:
                    section = content.split("## What I Learned")[1].split("---")[0].strip()
                    task_id = f.stem.split("_")[0]
                    lines.append(f"- **{task_id}**: {section[:200]}")
            except Exception:
                continue

        return "\n".join(lines) if len(lines) > 2 else ""


# Singleton
_learner: Optional[CrossTaskLearner] = None

def get_learner() -> CrossTaskLearner:
    global _learner
    if _learner is None:
        _learner = CrossTaskLearner()
    return _learner
