import json

from self_evolve.analyzer import FailureAnalyzer


def test_failure_analyzer(tmp_path) -> None:
    p = tmp_path / "eval.json"
    p.write_text(json.dumps({"score": 0.5, "failed": 2}), encoding="utf-8")

    lessons = FailureAnalyzer().analyze_eval_file(p)

    assert lessons
    assert lessons[0].category == "test_failure"
