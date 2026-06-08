from pathlib import Path

from self_evolve.scoring import ScoreExtractor


def test_extract_score_from_json(tmp_path: Path) -> None:
    p = tmp_path / "eval.json"
    p.write_text('{"score": 0.75}', encoding="utf-8")

    info = ScoreExtractor().extract_from_file(p)

    assert info.score == 0.75
