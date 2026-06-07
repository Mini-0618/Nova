"""Tests for tool calling improvements and training data collector."""
import sys
import os
import json
import tempfile
sys.path.insert(0, r'D:\codex-local')

from runtime.loop import (
    _build_messages, _TOOL_USE_REMINDER, SYSTEM_PROMPT,
    DecisionEngine, ActionType, Action, LoopConfig
)
from runtime.data_collector import DataCollector
from tools.executor import get_executor


# ── _build_messages tests ─────────────────────────────────────────────────

def test_build_messages_no_history():
    """Basic: task only, no history."""
    msgs = _build_messages("hello", [], "sys prompt")
    assert len(msgs) == 2  # system + user task
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "hello"


def test_build_messages_with_tool_use_reminder():
    """When last assistant message has no tool_calls, a reminder is injected."""
    history = [
        {"role": "user", "content": "do something"},
        {"role": "assistant", "content": "I will now create the file..."},
    ]
    msgs = _build_messages("task", history, "sys")
    # Should have: system + user + assistant + reminder + task
    roles = [m["role"] for m in msgs]
    assert roles == ["system", "user", "assistant", "user", "user"]
    # The reminder message should be present
    reminder_msgs = [m for m in msgs if m["content"] == _TOOL_USE_REMINDER]
    assert len(reminder_msgs) == 1


def test_build_messages_no_reminder_with_tool_calls():
    """When last assistant message HAS tool_calls, no reminder is injected."""
    history = [
        {"role": "user", "content": "do something"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "Write", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"success": true}'},
    ]
    msgs = _build_messages("task", history, "sys")
    reminder_msgs = [m for m in msgs if m.get("content") == _TOOL_USE_REMINDER]
    assert len(reminder_msgs) == 0


def test_system_prompt_has_cli_examples():
    """System prompt should contain CLI task examples."""
    assert "Write('script.py', code)" in SYSTEM_PROMPT
    assert "Bash('python script.py')" in SYSTEM_PROMPT
    assert "Bash('python --version')" in SYSTEM_PROMPT
    assert "ALWAYS call tools" in SYSTEM_PROMPT


# ── DecisionEngine tests ─────────────────────────────────────────────────

def test_decision_describe_pattern_low_confidence():
    """When model describes instead of executing, confidence should be 0.3."""
    executor = get_executor()
    config = LoopConfig()
    engine = DecisionEngine(executor, config)

    # Simulate LLM output that describes instead of doing
    output_items = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "Here is the code:\n```python\nprint('hi')\n```"}],
        }
    ]
    action = engine.decide(output_items)
    assert action.type == ActionType.RESPOND
    assert action.confidence == 0.3
    assert action.will_continue is True


def test_decision_step_pattern_low_confidence():
    """Step-by-step descriptions should also trigger low confidence."""
    executor = get_executor()
    config = LoopConfig()
    engine = DecisionEngine(executor, config)

    output_items = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "Step 1: Create the file\nStep 2: Run the script"}],
        }
    ]
    action = engine.decide(output_items)
    assert action.type == ActionType.RESPOND
    assert action.confidence == 0.3
    assert action.will_continue is True


def test_decision_real_response_high_confidence():
    """Legitimate final responses should have high confidence."""
    executor = get_executor()
    config = LoopConfig()
    engine = DecisionEngine(executor, config)

    output_items = [
        {
            "type": "message",
            "content": [{"type": "output_text", "text": "The task is complete. All tests pass."}],
        }
    ]
    action = engine.decide(output_items)
    assert action.type == ActionType.RESPOND
    assert action.confidence == 1.0
    assert action.will_continue is False


# ── DataCollector tests ──────────────────────────────────────────────────

def test_data_collector_record():
    """DataCollector should record and write JSONL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = DataCollector(session_id="test_session", data_dir=tmpdir)

        entry = collector.record(
            task="Create hello.py",
            messages_sent=[{"role": "user", "content": "create hello.py"}],
            llm_response={"choices": [{"message": {"content": "ok"}}]},
            tool_calls=[{"function": {"name": "Write", "arguments": "{}"}}],
            tool_results=[{"content": '{"success": true}', "success": True}],
            success=True,
            tokens_used=100,
            iteration=1,
        )

        assert entry["session_id"] == "test_session"
        assert entry["task"] == "Create hello.py"
        assert entry["success"] is True
        assert entry["tokens_used"] == 100
        assert entry["iteration"] == 1
        assert len(collector.records) == 1

        # Verify JSONL file was written
        fpath = os.path.join(tmpdir, "test_session.jsonl")
        assert os.path.exists(fpath)
        with open(fpath, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["task"] == "Create hello.py"


def test_data_collector_export_finetune():
    """DataCollector.export_finetune_format should produce instruction-input-output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        collector = DataCollector(session_id="test_export", data_dir=tmpdir)

        collector.record(
            task="Write a fibonacci function",
            messages_sent=[{"role": "user", "content": "write fibonacci"}],
            llm_response={"choices": []},
            tool_calls=[
                {"function": {"name": "Write", "arguments": '{"path": "fib.py"}'}},
            ],
            tool_results=[{"content": '{"success": true}', "success": True}],
            success=True,
            tokens_used=200,
            iteration=1,
        )

        out_path = collector.export_finetune_format()
        assert os.path.exists(out_path)

        with open(out_path, "r") as f:
            entries = [json.loads(line) for line in f if line.strip()]

        assert len(entries) == 1
        assert entries[0]["instruction"] == "Write a fibonacci function"
        assert "user:" in entries[0]["input"]
        assert "CALL Write" in entries[0]["output"]


def test_data_collector_load():
    """DataCollector.load should restore records from JSONL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write some data
        collector = DataCollector(session_id="test_load", data_dir=tmpdir)
        collector.record(
            task="test task",
            messages_sent=[],
            llm_response={},
            success=True,
            tokens_used=50,
        )

        # Load it back
        loaded = DataCollector.load("test_load", data_dir=tmpdir)
        assert len(loaded.records) == 1
        assert loaded.records[0]["task"] == "test task"
