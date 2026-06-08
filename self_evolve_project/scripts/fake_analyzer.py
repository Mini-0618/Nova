from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.eval).read_text(encoding="utf-8"))

    lessons = []

    if data.get("failed", 0) > 0:
        lessons.append(
            {
                "category": "failure",
                "message": f"failed cases: {data['failed']}",
                "suggestion": "Strengthen edge conditions, error handling, and test coverage.",
            }
        )
    else:
        lessons.append(
            {
                "category": "stable",
                "message": "no failures",
                "suggestion": "Keep strategy, small optimizations.",
            }
        )

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(lessons, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
