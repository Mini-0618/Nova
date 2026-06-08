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
    p.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
