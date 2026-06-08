from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path

from self_evolve.models import StepResult


class CommandRunner:
    def __init__(self, timeout_sec: float = 120) -> None:
        self.timeout_sec = timeout_sec

    def run(self, name: str, command: str, cwd: str | Path | None = None) -> StepResult:
        start = time.perf_counter()

        try:
            # On Windows, use shell=True with the command as string
            # to avoid shlex.split mangling paths
            import sys as _sys
            if _sys.platform == "win32":
                cmd = command
                use_shell = True
            else:
                cmd = shlex.split(command)
                use_shell = False

            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                shell=use_shell,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_sec,
            )

            runtime = time.perf_counter() - start

            return StepResult(
                name=name,
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout[-10000:],
                stderr=proc.stderr[-10000:],
                runtime_sec=runtime,
                ok=proc.returncode == 0,
            )

        except subprocess.TimeoutExpired as exc:
            runtime = time.perf_counter() - start

            return StepResult(
                name=name,
                command=command,
                returncode=124,
                stdout=str(exc.stdout or "")[-10000:],
                stderr=str(exc.stderr or "timeout")[-10000:],
                runtime_sec=runtime,
                ok=False,
            )
