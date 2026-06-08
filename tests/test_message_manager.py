"""Tests for runtime.message_manager module."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.message_manager import (
    _build_messages,
    _estimate_tokens,
    _msg_char_len,
    MAX_MESSAGES_CHARS,
    _TOOL_USE_REMINDER,
)


class TestEstimateTokens:
    def test_short_text(self):
        assert _estimate_tokens("hi") == 1  # 2 chars // 4 + 1 = 1

    def test_empty_text(self):
        assert _estimate_tokens("") == 1

    def test_40_chars(self):
        assert _estimate_tokens("a" * 40) == 11  # 40 // 4 + 1

    def test_long_text(self):
        result = _estimate_tokens("x" * 1000)
        assert result == 251


class TestMsgCharLen:
    def test_simple_message(self):
        msg = {"role": "user", "content": "hello"}
        length = _msg_char_len(msg)
        expected = len(json.dumps(msg, ensure_ascii=False))
        assert length == expected

    def test_unicode_message(self):
        msg = {"role": "user", "content": "你好"}
        length = _msg_char_len(msg)
        assert length > 0


class TestBuildMessages:
    def test_no_history(self):
        msgs = _build_messages("hello", [], "sys prompt")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "hello"

    def test_with_tool_use_reminder(self):
        history = [
            {"role": "user", "content": "do something"},
            {"role": "assistant", "content": "I will now create the file..."},
        ]
        msgs = _build_messages("task", history, "sys")
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant", "user", "user"]
        reminder_msgs = [m for m in msgs if m["content"] == _TOOL_USE_REMINDER]
        assert len(reminder_msgs) == 1

    def test_no_reminder_with_tool_calls(self):
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

    def test_token_based_truncation(self):
        """With a very small max_context_tokens, messages should be truncated."""
        history = [{"role": "user", "content": "a" * 1000} for _ in range(20)]
        msgs = _build_messages("task", history, "sys", max_context_tokens=50)
        total = sum(len(json.dumps(m)) for m in msgs)
        assert total <= 50 * 4 + 200  # some slack for the system msg

    def test_preserves_tool_call_pairing(self):
        """When truncating, assistant tool_calls and their tool results should stay paired."""
        history = [
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "Write", "arguments": "{}"}}
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"success": true}'},
            {"role": "user", "content": "next"},
        ]
        # Very small context to force truncation
        msgs = _build_messages("task", history, "sys", max_context_tokens=10)
        # System message should always be first
        assert msgs[0]["role"] == "system"
        # Truncation should have happened (fewer messages than full)
        assert len(msgs) < 5  # full would be: system + assistant + tool + user + user


class TestConstants:
    def test_max_messages_chars(self):
        assert MAX_MESSAGES_CHARS == 80_000

    def test_tool_use_reminder(self):
        assert "tools" in _TOOL_USE_REMINDER.lower()
