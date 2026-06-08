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
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
