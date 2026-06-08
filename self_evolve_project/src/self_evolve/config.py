from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")

    return json.loads(p.read_text(encoding="utf-8"))


def ensure_dirs(config: dict[str, Any]) -> dict[str, Path]:
    workspace = Path(config["workspace"])
    cycles = workspace / "cycles"
    logs = workspace / "logs"
    reports = workspace / "reports"

    for path in (workspace, cycles, logs, reports):
        path.mkdir(parents=True, exist_ok=True)

    return {
        "workspace": workspace,
        "cycles": cycles,
        "logs": logs,
        "reports": reports,
    }
