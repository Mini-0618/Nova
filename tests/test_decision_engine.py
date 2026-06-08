"""Tests for runtime.decision_engine module."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.decision_engine import (
    ActionType,
    Action,
    DecisionEngine,
    SYSTEM_PROMPT,
    CHAIN_OF_THOUGHT_PROMPT,
)
from tools.executor import get_executor


class TestActionType:
    def test_values(self):
        assert ActionType.CALL_TOOL.value == "call_tool"
        assert ActionType.RESPOND.value == "respond"
        assert ActionType.WAIT.value == "wait"
        assert ActionType.LOOP_END.value == "loop_end"
        assert ActionType.ERROR.value == "error"


class TestAction:
    def test_to_dict(self):
        action = Action(
            type=ActionType.CALL_TOOL,
            tool_name="Write",
            tool_args={"path": "test.py"},
            confidence=0.95,
            reasoning="calling tool",
        )
        d = action.to_dict()
        assert d["type"] == "call_tool"
        assert d["tool_name"] == "Write"
        assert d["tool_args"] == {"path": "test.py"}
        assert d["confidence"] == 0.95

    def test_defaults(self):
        action = Action(type=ActionType.RESPOND)
        assert action.tool_name is None
        assert action.tool_args is None
        assert action.confidence == 1.0
        assert action.will_continue is True


class TestDecisionEngine:
    def _make_engine(self, **config_overrides):
        """Create a DecisionEngine with a mock executor."""
        executor = get_executor()

        class MockConfig:
            trust_shell_commands = True
            allowed_commands = []
            blocked_commands = ["rm -rf /"]

        for k, v in config_overrides.items():
            setattr(MockConfig, k, v)

        return DecisionEngine(executor, MockConfig())

    def test_decide_empty_items(self):
        engine = self._make_engine()
        action = engine.decide([])
        assert action.type == ActionType.ERROR
        assert action.will_continue is False

    def test_decide_function_call(self):
        engine = self._make_engine()
        items = [{
            "type": "function_call",
            "name": "Write",
            "arguments": '{"path": "test.py", "content": "x"}',
            "call_id": "c1",
        }]
        action = engine.decide(items)
        assert action.type == ActionType.CALL_TOOL
        assert action.tool_name == "Write"
        assert action.tool_args == {"path": "test.py", "content": "x"}
        assert action.confidence == 0.95

    def test_decide_final_response(self):
        engine = self._make_engine()
        items = [{
            "type": "message",
            "content": [{"type": "output_text", "text": "The task is complete."}],
        }]
        action = engine.decide(items)
        assert action.type == ActionType.RESPOND
        assert action.response_text == "The task is complete."
        assert action.confidence == 1.0
        assert action.will_continue is False

    def test_decide_describe_pattern_low_confidence(self):
        engine = self._make_engine()
        items = [{
            "type": "message",
            "content": [{"type": "output_text", "text": "Here is the code:\n```python\nprint('hi')\n```"}],
        }]
        action = engine.decide(items)
        assert action.type == ActionType.RESPOND
        assert action.confidence == 0.3
        assert action.will_continue is True

    def test_decide_step_pattern_low_confidence(self):
        engine = self._make_engine()
        items = [{
            "type": "message",
            "content": [{"type": "output_text", "text": "Step 1: Create the file\nStep 2: Run the script"}],
        }]
        action = engine.decide(items)
        assert action.type == ActionType.RESPOND
        assert action.confidence == 0.3
        assert action.will_continue is True

    def test_check_command_safety_blocked(self):
        engine = self._make_engine()
        result = engine._check_command_safety("rm -rf /")
        assert result["allowed"] is False

    def test_check_command_safety_allowed(self):
        engine = self._make_engine()
        result = engine._check_command_safety("python hello.py")
        assert result["allowed"] is True

    def test_check_command_safety_allowlist(self):
        engine = self._make_engine(allowed_commands=["python", "pip"])
        result = engine._check_command_safety("python test.py")
        assert result["allowed"] is True
        result2 = engine._check_command_safety("rm -rf /")
        assert result2["allowed"] is False

    def test_execute_action_respond(self):
        engine = self._make_engine()
        action = Action(type=ActionType.RESPOND, response_text="hello")
        result = engine.execute_action(action)
        assert result["success"] is True
        assert result["text"] == "hello"

    def test_execute_action_error(self):
        engine = self._make_engine()
        action = Action(type=ActionType.ERROR, reasoning="something broke")
        result = engine.execute_action(action)
        assert result["success"] is False
        assert "something broke" in result["error"]

    def test_pending_calls_stored(self):
        engine = self._make_engine()
        items = [
            {"type": "function_call", "name": "Write", "arguments": '{"path":"a.py"}', "call_id": "c1"},
            {"type": "function_call", "name": "Bash", "arguments": '{"command":"ls"}', "call_id": "c2"},
        ]
        engine.decide(items)
        assert hasattr(engine, '_pending_calls')
        assert len(engine._pending_calls) == 1
        assert engine._pending_calls[0][1] == "Bash"


class TestSystemPrompts:
    def test_system_prompt_has_cli_examples(self):
        assert "Write('script.py', code)" in SYSTEM_PROMPT
        assert "Bash('python script.py')" in SYSTEM_PROMPT
        assert "ALWAYS call tools" in SYSTEM_PROMPT

    def test_chain_of_thought_prompt(self):
        assert "ANALYZE" in CHAIN_OF_THOUGHT_PROMPT
        assert "PLAN" in CHAIN_OF_THOUGHT_PROMPT
        assert "EXECUTE" in CHAIN_OF_THOUGHT_PROMPT
