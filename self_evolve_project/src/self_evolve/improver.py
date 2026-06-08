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

        out = prompt.rstrip() + "\n" + "\n".join(additions) + "\n"

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out, encoding="utf-8")
