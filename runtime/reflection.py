"""
Nova's Self-Reflection Module
After each task, generates a natural-language reflection on what happened.
Not a technical log - a thinking process description.

Nova's Innovation #3
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

REFLECTIONS_DIR = Path(__file__).parent.parent / "data" / "knowledge" / "reflections"


class ReflectionWriter:
    """Writes post-task reflections in Nova's voice."""

    def __init__(self):
        REFLECTIONS_DIR.mkdir(parents=True, exist_ok=True)

    def write_reflection(self, task_id: str, task_description: str,
                         tools_used: List[str], iterations: int,
                         passed: bool, error: str = "",
                         duration_s: float = 0, details: str = "") -> str:
        """
        Generate and save a reflection for a completed task.

        Returns the reflection text.
        """
        reflection = self._generate_reflection(
            task_id, task_description, tools_used, iterations,
            passed, error, duration_s, details
        )

        # Save to file
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{task_id}_{timestamp}.md"
        filepath = REFLECTIONS_DIR / filename
        filepath.write_text(reflection, encoding="utf-8")

        return reflection

    def _generate_reflection(self, task_id: str, task_description: str,
                             tools_used: List[str], iterations: int,
                             passed: bool, error: str,
                             duration_s: float, details: str) -> str:
        """Generate reflection text in Nova's voice."""

        # Determine what happened
        tool_sequence = " -> ".join(tools_used) if tools_used else "no tools"
        outcome = "succeeded" if passed else "failed"

        # Build reflection sections
        sections = []

        # What was the task?
        sections.append(f"## Task {task_id}")
        sections.append(f"**Question:** {task_description[:200]}")
        sections.append("")

        # What did I do?
        sections.append("## What I Did")
        if "file_read" in tools_used and "file_write" in tools_used:
            sections.append("I started by reading the relevant file to understand the current state. "
                          "Then I made the necessary changes and wrote the result.")
        elif "file_write" in tools_used and "bash" in tools_used:
            sections.append("I wrote the code first, then ran it to verify it works.")
        elif "file_read" in tools_used and "bash" in tools_used:
            sections.append("I read the code to understand it, then ran tests to check my understanding.")
        else:
            sections.append(f"I used this tool sequence: {tool_sequence}")

        sections.append(f"Iterations needed: {iterations}")
        sections.append("")

        # What went well or wrong?
        sections.append("## Reflection")
        if passed:
            if iterations <= 3:
                sections.append("This went smoothly. I understood the task quickly and executed it efficiently. "
                              "The key was reading the code first before making changes.")
            elif iterations <= 6:
                sections.append("Got it done, but it took a few tries. "
                              "I might have been able to be more decisive in my first attempt.")
            else:
                sections.append(f"Took {iterations} iterations - more than I'd like. "
                              "I probably re-read some files unnecessarily or tried a few wrong approaches "
                              "before finding the right one.")
        else:
            sections.append(f"Failed: {error[:200]}")
            if "file not found" in error.lower():
                sections.append("I think I described what to do instead of actually doing it. "
                              "Need to use tools directly, not explain my plan.")
            elif "assertion" in error.lower() or "expected" in error.lower():
                sections.append("My fix didn't match what was expected. "
                              "I should have read the spec more carefully or run the test first.")
            elif "import" in error.lower():
                sections.append("Import error - I likely got the module name wrong. "
                              "Should check actual file names before writing imports.")
            elif "token" in error.lower() or "iteration" in error.lower():
                sections.append("Ran out of context or iterations. "
                              "The task was too complex for the available budget, "
                              "or I got stuck in a loop reading the same files.")

        sections.append("")

        # What would I do differently?
        sections.append("## What I Learned")
        if passed and iterations <= 3:
            sections.append("Reading the file first and understanding the problem before acting works well. "
                          "Should do this for every task.")
        elif passed:
            sections.append("Got there in the end. Key lesson: be more confident in my first fix. "
                          "Don't re-read files I've already seen unless the context window forced it out.")
        else:
            sections.append("Need to be more careful about actually executing tools instead of describing them. "
                          "Also, always run the verification test after making changes.")

        # Metadata
        sections.append("")
        sections.append("---")
        sections.append(f"*Duration: {duration_s:.1f}s | Tools: {tool_sequence}*")

        return "\n".join(sections)

    def get_recent_reflections(self, limit: int = 10) -> List[Dict]:
        """Get recent reflections for learning injection."""
        reflections = []
        files = sorted(REFLECTIONS_DIR.glob("*.md"), reverse=True)
        for f in files[:limit]:
            try:
                content = f.read_text(encoding="utf-8")
                reflections.append({
                    "file": f.name,
                    "content": content[:500],
                    "task_id": f.stem.split("_")[0],
                })
            except Exception:
                continue
        return reflections

    def get_failure_reflections(self, limit: int = 5) -> List[Dict]:
        """Get reflections from failed tasks for learning."""
        all_reflections = self.get_recent_reflections(limit=50)
        return [r for r in all_reflections if "Failed" in r.get("content", "")][:limit]


# Singleton
_writer: Optional[ReflectionWriter] = None

def get_reflection_writer() -> ReflectionWriter:
    global _writer
    if _writer is None:
        _writer = ReflectionWriter()
    return _writer
