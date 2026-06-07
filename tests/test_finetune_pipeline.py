"""Tests for runtime.finetune_pipeline"""

import json
import tempfile
from pathlib import Path

import pytest

from runtime.finetune_pipeline import FinetunePipeline, _read_jsonl, _write_jsonl


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def tmp_path_factory():
    """Simple tmp dir helper."""
    import tempfile, shutil
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _make_training_file(dirpath: Path, name: str, records: list):
    """Write a JSONL training file."""
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    _write_jsonl(p, records)
    return p


def _make_eval_report(dirpath: Path, name: str, report: dict):
    """Write a JSON eval report."""
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / name
    with open(p, "w", encoding="utf-8") as f:
        json.dump(report, f)
    return p


def _make_lessons_file(dirpath: Path, lessons: list):
    """Write lessons.json."""
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / "lessons.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(lessons, f)
    return p


SAMPLE_TRAINING_RECORD = {
    "timestamp": "2026-06-07T10:00:00",
    "session_id": "test-session",
    "iteration": 1,
    "task": "Create a Python file that prints hello world",
    "messages_sent_summary": "user: Create hello.py",
    "messages_sent_count": 2,
    "llm_response": {"content": "OK"},
    "tool_calls": [
        {"function": {"name": "write_file", "arguments": '{"path":"hello.py"}'}}
    ],
    "tool_results": [
        {"content": "File written", "success": True}
    ],
    "success": True,
    "tokens_used": 500,
}

SAMPLE_EVAL_REPORT = {
    "timestamp": "2026-06-07 13:20:16",
    "total_tasks": 2,
    "passed": 1,
    "failed": 1,
    "pass_rate": 50.0,
    "results": [
        {
            "task_id": "E01",
            "category": "file_io",
            "difficulty": "easy",
            "title": "Create a file with content",
            "passed": True,
            "score": 1,
            "error": None,
            "duration_s": 1.5,
            "tools_used": ["write_file"],
            "tool_calls_total": 1,
            "tool_calls_success": 1,
            "needed_human": False,
            "introduced_regression": False,
            "changed_wrong_files": False,
            "patch_too_large": False,
            "details": "task OK",
        },
        {
            "task_id": "E02",
            "category": "bugfix",
            "difficulty": "medium",
            "title": "Fix the off-by-one error",
            "passed": False,
            "score": 0,
            "error": "IndexError at line 42",
            "duration_s": 3.0,
            "tools_used": ["read_file"],
            "tool_calls_total": 2,
            "tool_calls_success": 1,
            "needed_human": True,
            "introduced_regression": False,
            "changed_wrong_files": False,
            "patch_too_large": False,
            "details": "failed",
        },
    ],
}

SAMPLE_LESSONS = [
    {
        "id": "lesson-001",
        "pattern": "Model describes tool calls in text instead of using structured format",
        "fix": "Simplify system prompt, rely on tool schema definitions only",
        "category": "agent_loop",
        "source_task": "E41",
        "confidence": 0.9,
        "times_applied": 0,
        "times_successful": 0,
        "created_at": "2026-06-07",
    },
    {
        "id": "lesson-002",
        "pattern": "Calling non-existent method name on API object",
        "fix": "Check actual method signatures before calling",
        "category": "bugfix",
        "source_task": "E41",
        "confidence": 0.95,
        "times_applied": 0,
        "times_successful": 0,
        "created_at": "2026-06-07",
    },
]


# ------------------------------------------------------------------ #
# Collect tests
# ------------------------------------------------------------------ #

class TestCollect:
    def test_collect_from_training_dir(self, tmp_path_factory):
        tmp = tmp_path_factory
        training_dir = tmp / "training"
        _make_training_file(training_dir, "session1.jsonl", [SAMPLE_TRAINING_RECORD, SAMPLE_TRAINING_RECORD])

        pipeline = FinetunePipeline(training_dir=str(training_dir))
        entries = pipeline.collect_from_training_dir()

        assert len(entries) == 2
        assert entries[0]["instruction"] == "Create a Python file that prints hello world"
        assert entries[0]["source"] == "training"
        assert "CALL write_file" in entries[0]["output"]

    def test_collect_from_eval_reports(self, tmp_path_factory):
        tmp = tmp_path_factory
        reports_dir = tmp / "reports"
        _make_eval_report(reports_dir, "eval1.json", SAMPLE_EVAL_REPORT)

        pipeline = FinetunePipeline(eval_reports_dir=str(reports_dir))
        entries = pipeline.collect_from_eval_reports()

        assert len(entries) == 2
        assert entries[0]["source"] == "eval_report"
        assert entries[0]["category"] == "file_io"
        assert entries[1]["category"] == "bugfix"
        assert "successfully" in entries[0]["output"]
        assert "IndexError" in entries[1]["output"]

    def test_collect_from_lessons(self, tmp_path_factory):
        tmp = tmp_path_factory
        lessons_file = _make_lessons_file(tmp, SAMPLE_LESSONS)

        pipeline = FinetunePipeline(lessons_file=str(lessons_file))
        entries = pipeline.collect_from_lessons()

        assert len(entries) == 2
        assert entries[0]["source"] == "lesson"
        assert "lesson-001" in entries[0]["instruction"]
        assert "Simplify" in entries[0]["output"]

    def test_merge_all_combines_sources(self, tmp_path_factory):
        tmp = tmp_path_factory
        training_dir = tmp / "training"
        reports_dir = tmp / "reports"
        _make_training_file(training_dir, "s1.jsonl", [SAMPLE_TRAINING_RECORD])
        _make_eval_report(reports_dir, "e1.json", SAMPLE_EVAL_REPORT)
        _make_lessons_file(tmp, SAMPLE_LESSONS)

        pipeline = FinetunePipeline(
            training_dir=str(training_dir),
            eval_reports_dir=str(reports_dir),
            lessons_file=str(tmp / "lessons.json"),
        )
        entries = pipeline.merge_all()

        # 1 training + 2 eval + 2 lessons = 5
        assert len(entries) == 5
        sources = {e["source"] for e in entries}
        assert sources == {"training", "eval_report", "lesson"}

    def test_collect_empty_dirs(self, tmp_path_factory):
        tmp = tmp_path_factory
        pipeline = FinetunePipeline(
            training_dir=str(tmp / "empty1"),
            eval_reports_dir=str(tmp / "empty2"),
            lessons_file=str(tmp / "missing.json"),
        )
        entries = pipeline.merge_all()
        assert entries == []


# ------------------------------------------------------------------ #
# Deduplicate tests
# ------------------------------------------------------------------ #

class TestDeduplicate:
    def test_deduplicate_exact(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "Create a hello world script", "input": "", "output": "done", "source": "s", "category": "c"},
            {"instruction": "Create a hello world script", "input": "", "output": "done too", "source": "s", "category": "c"},
        ]
        result = pipeline.deduplicate(threshold=0.9)
        assert len(result) == 1

    def test_deduplicate_similar(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "Create a Python script that prints hello world to the console", "input": "", "output": "a", "source": "s", "category": "c"},
            {"instruction": "Create a Python script that prints hello world to the consle", "input": "", "output": "b", "source": "s", "category": "c"},
        ]
        result = pipeline.deduplicate(threshold=0.9)
        # These differ by only 2 chars so similarity > 0.95
        assert len(result) == 1

    def test_deduplicate_different_kept(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "Create a hello world script", "input": "", "output": "a", "source": "s", "category": "c"},
            {"instruction": "Fix the database connection timeout error in production", "input": "", "output": "b", "source": "s", "category": "c"},
        ]
        result = pipeline.deduplicate(threshold=0.9)
        assert len(result) == 2


# ------------------------------------------------------------------ #
# Filter quality tests
# ------------------------------------------------------------------ #

class TestFilterQuality:
    def test_filter_removes_short_instruction(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "hi", "input": "", "output": "some output here", "source": "s", "category": "c"},
            {"instruction": "Create a full Python web application with Flask", "input": "", "output": "done writing files", "source": "s", "category": "c"},
        ]
        result = pipeline.filter_quality()
        assert len(result) == 1
        assert "Flask" in result[0]["instruction"]

    def test_filter_removes_short_output(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "This is a valid instruction text", "input": "", "output": "ab", "source": "s", "category": "c"},
            {"instruction": "This is another valid instruction", "input": "", "output": "This is a proper output", "source": "s", "category": "c"},
        ]
        result = pipeline.filter_quality()
        assert len(result) == 1

    def test_filter_removes_empty(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "", "input": "", "output": "some output", "source": "s", "category": "c"},
            {"instruction": "Good instruction", "input": "", "output": "", "source": "s", "category": "c"},
        ]
        result = pipeline.filter_quality()
        assert len(result) == 0

    def test_filter_removes_non_string(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": 12345, "input": "", "output": "output", "source": "s", "category": "c"},
            {"instruction": "Good instruction here", "input": "", "output": ["not", "a", "string"], "source": "s", "category": "c"},
        ]
        result = pipeline.filter_quality()
        assert len(result) == 0


# ------------------------------------------------------------------ #
# Balance categories
# ------------------------------------------------------------------ #

class TestBalanceCategories:
    def test_balance_caps_at_smallest(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": f"task A{i}", "input": "", "output": "out", "source": "s", "category": "alpha"}
            for i in range(5)
        ] + [
            {"instruction": f"task B{i}", "input": "", "output": "out", "source": "s", "category": "beta"}
            for i in range(2)
        ]
        result = pipeline.balance_categories()
        # beta has 2, so alpha gets capped at 2 as well
        cats = [e["category"] for e in result]
        assert cats.count("alpha") == 2
        assert cats.count("beta") == 2

    def test_balance_with_max_per_category(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": f"task {i}", "input": "", "output": "out", "source": "s", "category": "x"}
            for i in range(10)
        ]
        result = pipeline.balance_categories(max_per_category=3)
        assert len(result) == 3


# ------------------------------------------------------------------ #
# Validate format
# ------------------------------------------------------------------ #

class TestValidateFormat:
    def test_validate_normalises_empty_input(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "some valid instruction", "input": None, "output": "valid output text"},
        ]
        result = pipeline.validate_format()
        assert len(result) == 1
        assert result[0]["input"] == ""

    def test_validate_keeps_valid(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "do something", "input": "context", "output": "result"},
        ]
        result = pipeline.validate_format()
        assert len(result) == 1


# ------------------------------------------------------------------ #
# Export tests
# ------------------------------------------------------------------ #

class TestExport:
    def _sample_data(self):
        return [
            {"instruction": "task 1", "input": "ctx1", "output": "out1", "source": "s", "category": "c"},
            {"instruction": "task 2", "input": "ctx2", "output": "out2", "source": "s", "category": "c"},
        ]

    def test_export_jsonl(self, tmp_path_factory):
        tmp = tmp_path_factory
        pipeline = FinetunePipeline()
        pipeline.data = self._sample_data()
        out = str(tmp / "out.jsonl")
        pipeline.export_jsonl(out)

        lines = Path(out).read_text().strip().split("\n")
        assert len(lines) == 2
        obj = json.loads(lines[0])
        assert obj["instruction"] == "task 1"

    def test_export_alpaca(self, tmp_path_factory):
        tmp = tmp_path_factory
        pipeline = FinetunePipeline()
        pipeline.data = self._sample_data()
        out = str(tmp / "alpaca.json")
        pipeline.export_alpaca(out)

        with open(out, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 2
        assert set(data[0].keys()) == {"instruction", "input", "output"}

    def test_export_chatml(self, tmp_path_factory):
        tmp = tmp_path_factory
        pipeline = FinetunePipeline()
        pipeline.data = self._sample_data()
        out = str(tmp / "chatml.jsonl")
        pipeline.export_chatml(out)

        lines = Path(out).read_text().strip().split("\n")
        assert len(lines) == 2
        obj = json.loads(lines[0])
        assert "messages" in obj
        msgs = obj["messages"]
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[2]["role"] == "assistant"


# ------------------------------------------------------------------ #
# Stats tests
# ------------------------------------------------------------------ #

class TestStats:
    def test_stats_empty(self):
        pipeline = FinetunePipeline()
        pipeline.data = []
        stats = pipeline.generate_stats()
        assert stats["total"] == 0

    def test_stats_with_data(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "task A is here", "input": "", "output": "result A", "source": "training", "category": "file_io"},
            {"instruction": "task B is here too", "input": "ctx", "output": "result B is longer output", "source": "eval_report", "category": "bugfix"},
        ]
        stats = pipeline.generate_stats()
        assert stats["total"] == 2
        assert stats["by_source"]["training"] == 1
        assert stats["by_source"]["eval_report"] == 1
        assert stats["by_category"]["file_io"] == 1
        assert stats["instruction_lengths"]["min"] > 0
        assert stats["output_lengths"]["max"] >= stats["output_lengths"]["min"]

    def test_stats_field_structure(self):
        pipeline = FinetunePipeline()
        pipeline.data = [
            {"instruction": "x" * 100, "input": "", "output": "y" * 200, "source": "s", "category": "c"},
        ]
        stats = pipeline.generate_stats()
        assert "total" in stats
        assert "by_source" in stats
        assert "by_category" in stats
        assert "instruction_lengths" in stats
        assert "output_lengths" in stats
        assert "generated_at" in stats


# ------------------------------------------------------------------ #
# End-to-end
# ------------------------------------------------------------------ #

class TestEndToEnd:
    def test_full_pipeline(self, tmp_path_factory):
        """Collect -> clean -> export -> stats in one flow."""
        tmp = tmp_path_factory
        training_dir = tmp / "training"
        reports_dir = tmp / "reports"

        # Create source data
        _make_training_file(training_dir, "s1.jsonl", [SAMPLE_TRAINING_RECORD])
        _make_eval_report(reports_dir, "e1.json", SAMPLE_EVAL_REPORT)
        _make_lessons_file(tmp, SAMPLE_LESSONS)

        # Collect
        pipeline = FinetunePipeline(
            training_dir=str(training_dir),
            eval_reports_dir=str(reports_dir),
            lessons_file=str(tmp / "lessons.json"),
        )
        raw = pipeline.merge_all()
        assert len(raw) == 5

        # Clean
        pipeline.validate_format()
        pipeline.deduplicate()
        pipeline.filter_quality()
        assert len(pipeline.data) > 0

        # Export
        alpaca_path = str(tmp / "alpaca.json")
        pipeline.export_alpaca(alpaca_path)
        with open(alpaca_path, "r", encoding="utf-8") as f:
            alpaca = json.load(f)
        assert len(alpaca) == len(pipeline.data)

        chatml_path = str(tmp / "chatml.jsonl")
        pipeline.export_chatml(chatml_path)
        assert Path(chatml_path).exists()

        # Stats
        stats = pipeline.generate_stats()
        assert stats["total"] == len(pipeline.data)
