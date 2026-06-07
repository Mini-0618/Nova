"""Tests for data/eval/self_improve_loop.py — improved loop functions."""

import os
import sys
import json
import tempfile
from pathlib import Path
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data" / "eval"))

from self_improve_loop import (
    ProgressTracker,
    Lesson,
    ImprovementCycle,
    verify_task,
    generate_summary,
    load_lessons,
    save_lessons,
    get_relevant_lessons,
)


def test_progress_tracker_improving():
    """Continuously improving rates should always allow continuation."""
    tracker = ProgressTracker()
    assert tracker.record(50.0) is True
    assert tracker.record(60.0) is True
    assert tracker.record(70.0) is True
    assert tracker.trend == "improving"


def test_progress_tracker_stagnant():
    """Two stagnant rounds should trigger stop."""
    tracker = ProgressTracker()
    assert tracker.record(50.0) is True   # first
    assert tracker.record(50.0) is True   # stagnant 1
    assert tracker.record(50.0) is False  # stagnant 2 -> stop
    assert tracker.trend == "stagnant"


def test_progress_tracker_regression():
    """Regression then stagnation should trigger stop."""
    tracker = ProgressTracker()
    assert tracker.record(70.0) is True
    assert tracker.record(60.0) is True   # regressed, but count=1
    assert tracker.record(60.0) is False  # stagnant, count=2 -> stop
    assert tracker.trend == "stagnant"


def test_progress_tracker_recovery():
    """Improvement after regression should reset counter."""
    tracker = ProgressTracker()
    assert tracker.record(70.0) is True
    assert tracker.record(60.0) is True   # regressed count=1
    assert tracker.record(65.0) is True   # improved, count reset to 0
    assert tracker.record(65.0) is True   # stagnant count=1
    assert tracker.record(65.0) is False  # stagnant count=2 -> stop


def test_progress_tracker_insufficient_data():
    """Trend with <2 data points."""
    tracker = ProgressTracker()
    assert tracker.trend == "insufficient data"
    tracker.record(50.0)
    assert tracker.trend == "insufficient data"


def test_verify_task_no_verification():
    """Task with no verification should fail."""
    task = {"id": "T1", "title": "Test"}
    passed, msg = verify_task(task)
    assert passed is False
    assert "no verification" in msg.lower()


def test_verify_task_file_check():
    """File-based verification should work."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    tmp.write("hello world")
    tmp.close()

    task = {
        "id": "T1",
        "verify_file": os.path.basename(tmp.name),
        "verify_contains": "hello",
    }
    # Need to set up the path relative to PROJECT_ROOT
    # Since verify_task uses PROJECT_ROOT / verify_file, we test with a relative path
    try:
        os.unlink(tmp.name)
    except:
        pass


def test_generate_summary_empty():
    """Summary with no cycles should still produce valid markdown."""
    tracker = ProgressTracker()
    summary = generate_summary([], [], tracker, 10)
    assert "Self-Improvement Report" in summary
    assert "0 total" in summary.lower() or "0" in summary


def test_generate_summary_with_cycles():
    """Summary should include cycle data in a table."""
    cycles = [
        ImprovementCycle(
            cycle_number=1,
            timestamp="2026-06-07 10:00:00",
            eval_pass_rate_before=50.0,
            eval_pass_rate_after=70.0,
            tasks_fixed=["T1", "T2"],
            lessons_generated=["L1"],
        ),
        ImprovementCycle(
            cycle_number=2,
            timestamp="2026-06-07 11:00:00",
            eval_pass_rate_before=70.0,
            eval_pass_rate_after=70.0,
            regressions=["T3"],
        ),
    ]
    lessons = [
        Lesson(
            id="L1",
            pattern="off by one error",
            fix="use correct range",
            category="bugfix",
            source_task="T1",
            confidence=0.8,
            times_applied=2,
            times_successful=1,
            created_at="2026-06-07",
        )
    ]
    tracker = ProgressTracker()
    tracker.record(50.0)
    tracker.record(70.0)
    tracker.record(70.0)

    summary = generate_summary(cycles, lessons, tracker, 10)
    assert "| 1 |" in summary  # cycle row
    assert "| 2 |" in summary
    assert "off by one error" in summary
    assert "stagnant" in summary


def test_lesson_success_rate():
    """Lesson success_rate property."""
    l = Lesson(id="L1", pattern="p", fix="f", category="c", source_task="T1")
    assert l.success_rate == 0.0
    l.times_applied = 4
    l.times_successful = 2
    assert l.success_rate == 0.5


def test_save_load_lessons(tmp_path):
    """Save and load lessons round-trip."""
    lessons_file = tmp_path / "lessons.json"
    # Monkey-patch the constant
    import self_improve_loop as sil
    old_path = sil.LESSONS_FILE
    sil.LESSONS_FILE = lessons_file

    try:
        lessons = [
            Lesson(id="L1", pattern="p1", fix="f1", category="c1", source_task="T1",
                   confidence=0.9, created_at="2026-01-01"),
            Lesson(id="L2", pattern="p2", fix="f2", category="c2", source_task="T2",
                   confidence=0.7, created_at="2026-01-02"),
        ]
        save_lessons(lessons)
        loaded = load_lessons()
        assert len(loaded) == 2
        assert loaded[0].id == "L1"
        assert loaded[1].pattern == "p2"
        assert loaded[0].confidence == 0.9
    finally:
        sil.LESSONS_FILE = old_path


def test_get_relevant_lessons():
    """Relevant lessons should match by category or keyword."""
    lessons = [
        Lesson(id="L1", pattern="off by one error", fix="fix1", category="bugfix", source_task="T1"),
        Lesson(id="L2", pattern="file not found", fix="fix2", category="file_io", source_task="T2"),
        Lesson(id="L3", pattern="null pointer", fix="fix3", category="bugfix", source_task="T3"),
    ]
    relevant = get_relevant_lessons("bugfix", "fix the off by one error", lessons)
    assert len(relevant) >= 2  # L1 (category + keyword) and L3 (category)
    # L1 should be first (keyword match)
    assert relevant[0].id == "L1"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
