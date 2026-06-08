"""Tests for runtime.data_collector module."""

import json
import tempfile
from pathlib import Path

from runtime.data_collector import DataCollector, _summarize_messages, _truncate_response


class TestSummarizeMessages:
    def test_basic_messages(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        summary = _summarize_messages(messages)
        assert "user: hello" in summary
        assert "assistant: hi there" in summary

    def test_structured_content(self):
        messages = [
            {"role": "user", "content": [{"text": "hello"}, {"text": "world"}]},
        ]
        summary = _summarize_messages(messages)
        assert "hello" in summary
        assert "world" in summary

    def test_tool_calls_in_summary(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "read_file", "arguments": "{}"}},
                ],
            }
        ]
        summary = _summarize_messages(messages)
        assert "read_file" in summary

    def test_max_chars_respected(self):
        messages = [{"role": "user", "content": "x" * 1000}]
        summary = _summarize_messages(messages, max_chars=50)
        assert len(summary) <= 50


class TestTruncateResponse:
    def test_non_dict_input(self):
        result = _truncate_response("not a dict")
        assert "raw" in result
        assert "not a dict" in result["raw"]

    def test_truncates_long_strings(self):
        resp = {"key": "x" * 5000}
        result = _truncate_response(resp, max_chars=100)
        assert len(result["key"]) < len(resp["key"])
        assert "truncated" in result["key"].lower()

    def test_preserves_short_strings(self):
        resp = {"key": "short"}
        result = _truncate_response(resp)
        assert result["key"] == "short"


class TestDataCollector:
    def test_init_creates_dir(self, tmp_path):
        data_dir = tmp_path / "new_dir"
        collector = DataCollector("test", data_dir=str(data_dir))
        assert data_dir.exists()

    def test_record_adds_to_records(self, tmp_path):
        collector = DataCollector("test", data_dir=str(tmp_path))
        entry = collector.record(
            task="do something",
            messages_sent=[{"role": "user", "content": "hi"}],
            llm_response={"choices": [{"text": "ok"}]},
        )
        assert len(collector.get_records()) == 1
        assert entry["task"] == "do something"

    def test_record_appends_to_jsonl(self, tmp_path):
        collector = DataCollector("test", data_dir=str(tmp_path))
        collector.record(
            task="task1",
            messages_sent=[{"role": "user", "content": "a"}],
            llm_response={},
        )
        collector.record(
            task="task2",
            messages_sent=[{"role": "user", "content": "b"}],
            llm_response={},
        )
        file_path = tmp_path / "test.jsonl"
        lines = file_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["task"] == "task1"
        assert json.loads(lines[1])["task"] == "task2"

    def test_load_roundtrip(self, tmp_path):
        collector = DataCollector("roundtrip", data_dir=str(tmp_path))
        collector.record(
            task="loaded task",
            messages_sent=[{"role": "user", "content": "test"}],
            llm_response={"answer": 42},
            success=True,
        )
        loaded = DataCollector.load("roundtrip", data_dir=str(tmp_path))
        assert len(loaded.get_records()) == 1
        assert loaded.get_records()[0]["task"] == "loaded task"
        assert loaded.get_records()[0]["success"] is True

    def test_export_finetune_format(self, tmp_path):
        collector = DataCollector("export", data_dir=str(tmp_path))
        collector.record(
            task="write code",
            messages_sent=[{"role": "user", "content": "do it"}],
            llm_response={"text": "ok"},
            tool_calls=[
                {"function": {"name": "write_file", "arguments": '{"path": "a.py"}'}},
            ],
            tool_results=[
                {"content": "written", "success": True},
            ],
        )
        out_path = str(tmp_path / "finetune_out.jsonl")
        result = collector.export_finetune_format(out_path)
        assert result == out_path
        data = Path(out_path).read_text(encoding="utf-8")
        entry = json.loads(data.strip())
        assert entry["instruction"] == "write code"
        assert "CALL write_file" in entry["output"]
        assert "RESULT [OK]" in entry["output"]

    def test_save_returns_path(self, tmp_path):
        collector = DataCollector("save_test", data_dir=str(tmp_path))
        path = collector.save()
        assert "save_test.jsonl" in path

    def test_task_truncated_at_500(self, tmp_path):
        collector = DataCollector("trunc", data_dir=str(tmp_path))
        long_task = "x" * 1000
        entry = collector.record(
            task=long_task,
            messages_sent=[],
            llm_response={},
        )
        assert len(entry["task"]) == 500
