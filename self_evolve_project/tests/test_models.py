from self_evolve.models import CycleResult


def test_cycle_result_model() -> None:
    item = CycleResult(
        cycle=1,
        baseline_score=0.7,
        candidate_score=0.8,
        improved=True,
        promoted=True,
        baseline_eval="a.json",
        candidate_eval="b.json",
        lessons="lessons.json",
        candidate_prompt="prompt.md",
        created_at=1.0,
    )

    assert item.improved is True
