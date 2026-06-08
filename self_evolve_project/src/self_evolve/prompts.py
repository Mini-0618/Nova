from __future__ import annotations

import shutil
import time
from pathlib import Path


class PromptManager:
    def __init__(self, current_prompt: str | Path) -> None:
        self.current_prompt = Path(current_prompt)

    def promote(self, candidate_prompt: str | Path) -> None:
        candidate = Path(candidate_prompt)

        if not candidate.exists():
            raise FileNotFoundError(str(candidate))

        self.current_prompt.parent.mkdir(parents=True, exist_ok=True)

        if self.current_prompt.exists():
            backup = self.current_prompt.with_suffix(
                self.current_prompt.suffix + f".bak_{int(time.time())}"
            )
            shutil.copy2(self.current_prompt, backup)

        shutil.copy2(candidate, self.current_prompt)
