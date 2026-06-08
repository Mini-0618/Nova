import json

from self_evolve.improver import PromptImprover


def test_prompt_improver(tmp_path) -> None:
    prompt = tmp_path / "prompt.md"
    lessons = tmp_path / "lessons.json"
    out = tmp_path / "out.md"

    prompt.write_text("hello", encoding="utf-8")
    lessons.write_text(json.dumps([{"suggestion": "fix boundary"}]), encoding="utf-8")

    PromptImprover().improve(prompt, lessons, out)

    assert "fix boundary" in out.read_text(encoding="utf-8")
