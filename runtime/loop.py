"""
Codex-Local Auto-Loop Engine
The core decision engine: receives LLM output, decides next action, executes automatically.
No human confirmation needed. Every action is logged and can be recovered.
"""

import os
import json
import logging
import time
import asyncio
import threading
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

import sys as _sys
_root = Path(__file__).parent.parent
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tools.executor import ToolExecutor, get_executor, TOOL_DEFINITIONS  # noqa: E402
from runtime.session import SessionManager, get_manager, Session  # noqa: E402
from runtime.memory import MemoryManager, get_memory_manager  # noqa: E402
from runtime.data_collector import DataCollector  # noqa: E402

# Import from refactored modules
from runtime.decision_engine import (  # noqa: E402
    ActionType, Action, DecisionEngine,
    SYSTEM_PROMPT, CHAIN_OF_THOUGHT_PROMPT,
)
from runtime.message_manager import (  # noqa: E402
    _build_messages, _estimate_tokens, _msg_char_len,
    MAX_MESSAGES_CHARS, _TOOL_USE_REMINDER,
)
from runtime.llm_client import (  # noqa: E402
    _call_llm_async, _parse_sse_stream, _convert_chat_to_response_format,
    _resolve_api_url, _resolve_api_key, _resolve_api_key_for_provider,
    _infer_provider, _verify_model, list_available_models,
    _MODEL_PROVIDER_MAP, _convert_tools_to_openai_format, _extract_output_items,
)

_log = logging.getLogger(__name__)

# ─── Backward-compatible re-exports ────────────────────────────────────────
# All public names are importable from runtime.loop

__all__ = [
    # Config
    "LoopConfig",
    "SYSTEM_PROMPT",
    "CHAIN_OF_THOUGHT_PROMPT",
    # Decision types
    "ActionType",
    "Action",
    "DecisionEngine",
    # Message functions
    "_build_messages",
    "_estimate_tokens",
    "_msg_char_len",
    "MAX_MESSAGES_CHARS",
    "_TOOL_USE_REMINDER",
    # LLM functions
    "_call_llm_async",
    "_parse_sse_stream",
    "_convert_chat_to_response_format",
    "_resolve_api_url",
    "_resolve_api_key",
    "_resolve_api_key_for_provider",
    "_infer_provider",
    "_verify_model",
    "list_available_models",
    "_MODEL_PROVIDER_MAP",
    "_convert_tools_to_openai_format",
    "_extract_output_items",
    # Loop classes
    "CodexLoop",
    "EnhancedCodexLoop",
    # Cost
    "COST_PER_1K",
    "_estimate_cost",
    # Runners
    "run_automated",
    "run_enhanced",
]


# ─── LoopConfig ───────────────────────────────────────────────────────────

@dataclass
class LoopConfig:
    max_iterations: int = 100
    max_tokens_per_iteration: int = 4096
    auto_save_interval_sec: int = 30
    trust_code_execution: bool = True
    trust_file_writes: bool = True
    trust_shell_commands: bool = True
    max_output_tokens: int = 2048
    temperature: float = 0.7
    model: str = "deepseek-chat"
    provider: str = ""  # auto-detect from env
    system_prompt: str = SYSTEM_PROMPT
    # Multi-round reasoning settings
    enable_multi_round_reasoning: bool = False
    reasoning_rounds: int = 3
    reasoning_temperature: float = 0.3  # Lower temperature for reasoning
    chain_of_thought: bool = True  # Enable Chain-of-Thought prompting
    # Smart routing settings
    enable_smart_routing: bool = False  # Enable intelligent model selection
    monthly_budget: float = 50.0  # Monthly budget in dollars
    prefer_local: bool = False  # Prefer local models (Ollama)
    quality_threshold: float = 0.0  # Minimum quality score (0-1)
    # Memory system settings
    enable_memory: bool = True  # Enable memory system
    memory_context_max: int = 5  # Max memories to inject into context
    auto_remember: bool = True  # Auto-remember important interactions
    memory_importance_threshold: float = 0.6  # Threshold for auto-remembering
    # Workspace settings
    workspace: str = ""  # Working directory for file operations
    # Proxy settings -- only applied per CodexLoop instance, not globally at import
    clear_proxy_env: bool = True  # Unset proxy env vars during loop execution
    # Context management
    max_context_tokens: int = 8000  # Max tokens in context window (1 token ~= 4 chars)
    # Token budget control
    max_total_tokens: int = 100000  # Total token budget for a single run_task()
    # Security sandbox settings
    allowed_commands: List[str] = field(default_factory=list)  # if non-empty, only these are allowed
    blocked_commands: List[str] = field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", "format", "shutdown", "regedit",
        "mkfs", "dd if=", ":(){:|:&};:", "> /dev/sda",
    ])
    require_confirmation: bool = True  # require user confirmation for dangerous commands
    # Streaming settings
    stream: bool = False  # Enable streaming output
    # Model fallback settings
    fallback_models: List[str] = field(default_factory=list)  # Models to try when primary fails
    fallback_threshold: int = 3  # Consecutive failures before auto-fallback


# ─── Run State ────────────────────────────────────────────────────────────

@dataclass
class _RunState:
    """Mutable state for a single run_task() invocation."""
    session_id: str
    messages: List[Dict]
    message_history: List[Dict]
    data_collector: Any
    total_input_tokens: int = 0
    total_output_tokens: int = 0


# ─── Loop Helpers Mixin ──────────────────────────────────────────────────

class _CodexLoopHelpers:
    """Helper methods for CodexLoop, extracted to keep the main class focused."""

    def _apply_smart_routing(self, task: str) -> None:
        """Apply smart routing to select optimal model."""
        from runtime.smart_router import get_router
        router = get_router(monthly_budget=self.config.monthly_budget, prefer_local=self.config.prefer_local)
        result = router.route(task=task, require_tools=True, quality_threshold=self.config.quality_threshold)
        self.config.model = result["model_config"].model
        self.config.provider = result["model_config"].provider
        self._notify("routing", {"complexity": result["complexity"].value, "model": result["model_key"],
                                  "reason": result["reason"], "estimated_cost": result["estimated_cost"]})

    def _inject_memory_context(self, task: str) -> str:
        """Build system prompt with memory context injection."""
        system_prompt = self.config.system_prompt
        if self.memory_mgr and self.config.memory_context_max > 0:
            ctx = self.memory_mgr.get_relevant_memories_for_task(task, max_memories=self.config.memory_context_max)
            if ctx:
                system_prompt = f"{system_prompt}\n\n{ctx}"
        return system_prompt

    def _init_run(self, task: str, session_id: Optional[str]) -> _RunState:
        """Initialize run context: session, memory, messages, data collector."""
        if self.config.enable_smart_routing:
            self._apply_smart_routing(task)
        if session_id:
            self._current_session = self.session_mgr.get_session(session_id)
        if not self._current_session:
            self._current_session = self.session_mgr.create_session(
                model=self.config.model, provider=self.config.provider, metadata={"task": task})
        sid = self._current_session.id
        if self.memory_mgr:
            self.memory_mgr.set_session(sid)
            self.memory_mgr.store(f"Task: {task}", importance=0.8, tags=["task", "current"], source="user")
        system_prompt = self._inject_memory_context(task)
        messages = _build_messages(task, [], system_prompt, max_context_tokens=self.config.max_context_tokens)
        return _RunState(session_id=sid, messages=messages, message_history=[],
                         data_collector=DataCollector(session_id=sid))

    def _make_stream_cb(self) -> Optional[Callable]:
        """Build streaming callback if streaming is enabled."""
        if not self.config.stream:
            return None
        def cb(chunk: str):
            self._notify("stream_chunk", {"iteration": self._iteration, "chunk": chunk})
        return cb

    async def _call_llm_with_fallback(self, messages: List[Dict], stream_cb: Optional[Callable]) -> Optional[Dict]:
        """Call LLM with auto-fallback to backup models on failure."""
        try:
            return await _call_llm_async(messages, self.config, _resolve_api_key(),
                                          self.config.provider, self.config.model, stream_callback=stream_cb)
        except Exception as err:
            self._consecutive_failures += 1
            if (self.config.fallback_models and self._consecutive_failures >= self.config.fallback_threshold):
                new_model = self._try_fallback()
                if new_model:
                    self._notify("auto_fallback", {"new_model": new_model, "error": str(err)[:200]})
                    return await _call_llm_async(messages, self.config, _resolve_api_key(),
                                                  self.config.provider, self.config.model, stream_callback=stream_cb)
                self.error = f"All models failed: {err}"
                self.status = "error: all models failed"
                self._running = False
                return None
            self._notify("llm_failure", {"consecutive_failures": self._consecutive_failures, "error": str(err)[:200]})
            return None

    def _track_usage(self, response: Dict, session_id: str) -> tuple:
        """Track token usage and update session. Returns (input_tok, output_tok)."""
        usage = response.get("usage", {})
        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("completion_tokens", 0)
        self.session_mgr.update_tokens(session_id, input_tok, output_tok,
                                        cost=_estimate_cost(input_tok, output_tok, self.config.provider))
        return input_tok, output_tok

    def _check_token_budget(self) -> bool:
        """Check if token budget is exceeded. Returns True if exceeded."""
        if self.config.max_total_tokens > 0 and self.total_tokens_used >= self.config.max_total_tokens:
            self.error = f"token_budget_exceeded ({self.total_tokens_used}/{self.config.max_total_tokens})"
            self.status = "token_budget_exceeded"
            self._running = False
            self._notify("token_budget_exceeded", {"total_tokens": self.total_tokens_used, "budget": self.config.max_total_tokens})
            return True
        return False

    def _build_assistant_msg(self, output_items: List[Dict]) -> Dict:
        """Build assistant message dict from output items."""
        msg = {"role": "assistant", "content": ""}
        if any(item.get("type") == "function_call" for item in output_items):
            msg["tool_calls"] = [{
                "id": item.get("call_id") or f"auto_{id(item)}", "type": "function",
                "function": {"name": item.get("name", ""), "arguments": item.get("arguments", "{}")}
            } for item in output_items if item.get("type") == "function_call"]
        return msg

    def _enforce_context_window(self, messages: List[Dict]) -> List[Dict]:
        """Truncate oldest messages when context window is exceeded."""
        if len(messages) <= 2:
            return messages
        max_chars = self.config.max_context_tokens * 4 if self.config.max_context_tokens > 0 else MAX_MESSAGES_CHARS
        total_chars = sum(_msg_char_len(m) for m in messages)
        if total_chars <= max_chars:
            return messages
        system_msg, recent = messages[0], messages[1:]
        recent, total_chars = self._trim_old_messages(system_msg, recent, max_chars)
        recent = self._trim_orphan_tool_results(system_msg, recent)
        return [system_msg] + recent

    def _trim_old_messages(self, system_msg: Dict, recent: list, max_chars: int) -> tuple:
        """Remove oldest messages until within char limit. Returns (recent, total_chars)."""
        total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in recent)
        while recent and total_chars > max_chars:
            removed = recent.pop(0)
            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                if recent and recent[0].get("role") == "tool":
                    recent.pop(0)
            total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in recent)
        return recent, total_chars

    def _trim_orphan_tool_results(self, system_msg: Dict, recent: list) -> list:
        """Remove orphan tool results at the start of message list."""
        while recent and recent[0].get("role") == "tool":
            recent.pop(0)
        return recent

    def _find_call_id(self, action: Action, output_items: List[Dict]) -> Optional[str]:
        """Find the call_id for a tool call from output items."""
        for item in output_items:
            if item.get("type") == "function_call" and item.get("name") == action.tool_name:
                return item.get("call_id")
        return f"auto_{id(action)}"

    def _append_tool_result(self, call_id: str, result: Any, action: Action, state: _RunState) -> None:
        """Append tool result to messages and session."""
        result_str = json.dumps(result, ensure_ascii=False, default=str)
        # Truncate oversized tool results to prevent context window overflow
        MAX_RESULT_CHARS = 20_000
        if len(result_str) > MAX_RESULT_CHARS:
            result_str = result_str[:MAX_RESULT_CHARS] + '... [TRUNCATED - result too large]'
        msg = {"role": "tool", "tool_call_id": call_id, "content": result_str}
        state.messages.append(msg)
        state.message_history.append(msg)
        self.session_mgr.append_message(state.session_id, msg)
        self.session_mgr.append_tool_result(state.session_id, {
            "iteration": self._iteration, "tool": action.tool_name, "args": action.tool_args,
            "success": result.get("success") if isinstance(result, dict) else False,
            "timestamp": int(time.time())})

    def _track_tool_decision(self, action: Action, result: Any) -> None:
        """Track tool call decision for memory."""
        self._key_decisions.append({
            "iteration": self._iteration, "tool": action.tool_name,
            "success": result.get("success") if isinstance(result, dict) else False})

    def _remember_tool_result(self, action: Action, result: Any) -> None:
        """Store important tool results in memory."""
        if not self.memory_mgr or not self.config.auto_remember:
            return
        try:
            self._record_tool_memory(action, result)
        except Exception:
            _log.warning("Failed to store tool execution in memory", exc_info=True)

    def _record_tool_memory(self, action: Action, result: Any) -> None:
        """Record tool result details to memory (extracted for clarity)."""
        if not isinstance(result, dict):
            return
        success = result.get("success", False)
        if not success:
            error_msg = result.get("error", "")
            if error_msg:
                self.memory_mgr.store(f"Tool error ({action.tool_name}): {error_msg}",
                                       importance=0.7, tags=["error", action.tool_name], source="tool_execution")
            return
        file_tools = ("write_file", "edit_file", "create_directory")
        if action.tool_name in file_tools:
            fp = (action.tool_args or {}).get("path", "")
            if fp:
                self.memory_mgr.store(f"Modified file: {fp}", importance=0.5,
                                       tags=["file", "modified", action.tool_name], source="tool_execution")

    async def _execute_pending_calls(self, state: _RunState) -> None:
        """Execute remaining pending tool calls from same LLM response."""
        pending = getattr(self.decision_engine, '_pending_calls', [])
        while pending:
            call_id, tool_name, tool_args = pending.pop(0)
            self._notify("iteration", {"iteration": self._iteration, "session_id": state.session_id,
                                        "action": "executing_tool", "tool": tool_name, "args": tool_args})
            result = self.decision_engine.execute_action(
                Action(type=ActionType.CALL_TOOL, tool_name=tool_name, tool_args=tool_args))
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            # Truncate oversized tool results to prevent context window overflow
            MAX_RESULT_CHARS = 20_000
            if len(result_str) > MAX_RESULT_CHARS:
                result_str = result_str[:MAX_RESULT_CHARS] + '... [TRUNCATED - result too large]'
            msg = {"role": "tool", "tool_call_id": call_id, "content": result_str}
            state.messages.append(msg)
            state.message_history.append(msg)
            self.session_mgr.append_tool_result(state.session_id, {
                "iteration": self._iteration, "tool": tool_name, "args": tool_args,
                "success": result.get("success") if isinstance(result, dict) else False,
                "timestamp": int(time.time())})
            self.decision_engine._pending_calls = pending

    def _record_tool_iteration(self, task: str, assistant_msg: Dict, response: Dict,
                                state: _RunState, input_tok: int, output_tok: int, result: Any) -> None:
        """Record training data for a tool iteration."""
        try:
            tc_list = assistant_msg.get("tool_calls", [])
            tool_results = [{"tool_call_id": m.get("tool_call_id", ""), "content": m.get("content", ""), "success": True}
                             for m in state.messages if m.get("role") == "tool"]
            state.data_collector.record(
                task=task, messages_sent=state.messages[:-1], llm_response=response,
                tool_calls=tc_list, tool_results=tool_results,
                success=result.get("success") if isinstance(result, dict) else False,
                tokens_used=input_tok + output_tok, iteration=self._iteration)
        except Exception:
            _log.warning("Failed to collect training data for iteration %d", self._iteration, exc_info=True)

    def _maybe_checkpoint(self, session_id: str) -> None:
        """Save checkpoint if enough time has elapsed."""
        if time.time() - self._last_save > self.config.auto_save_interval_sec:
            self.session_mgr.checkpoint(self._current_session)
            self._last_save = time.time()
            self._notify("checkpoint", {"session_id": session_id})

    def _handle_respond(self, action: Action, task: str, state: _RunState) -> Optional[str]:
        """Handle RESPOND action. Returns final text or None to continue."""
        if action.will_continue:
            return None
        try:
            state.data_collector.record(task=task, messages_sent=state.messages, llm_response={},
                                         tool_calls=[], tool_results=[], success=True,
                                         tokens_used=self.total_tokens_used, iteration=self._iteration)
        except Exception:
            _log.warning("Failed to record final response training data", exc_info=True)
        self.status = "completed"
        self._running = False
        self._current_session.status = "completed"
        self.session_mgr.update_session(self._current_session)
        return action.response_text or ""

    async def _handle_tool_calls(self, action: Action, output_items: List[Dict], state: _RunState,
                                  task: str, assistant_msg: Dict, response: Dict,
                                  input_tok: int, output_tok: int) -> None:
        """Handle CALL_TOOL action: execute tool, track results, handle pending calls."""
        call_id = self._find_call_id(action, output_items)
        self._notify("iteration", {"iteration": self._iteration, "session_id": state.session_id,
                                    "action": "executing_tool", "tool": action.tool_name, "args": action.tool_args})
        result = self.decision_engine.execute_action(action)
        self._append_tool_result(call_id, result, action, state)
        self._track_tool_decision(action, result)
        self._remember_tool_result(action, result)
        await self._execute_pending_calls(state)
        self._record_tool_iteration(task, assistant_msg, response, state, input_tok, output_tok, result)
        self._maybe_checkpoint(state.session_id)

    async def _run_iteration(self, task: str, state: _RunState) -> Optional[str]:
        """Execute a single iteration of the main loop. Returns final text or None."""
        self._iteration += 1
        self.iteration_count = self._iteration
        self.status = f"iterating ({self._iteration})"
        self._notify("iteration", {"iteration": self._iteration, "session_id": state.session_id, "action": "calling_llm"})
        # Enforce context window BEFORE calling LLM to prevent token overflow
        # from accumulated tool results in previous iterations
        state.messages = self._enforce_context_window(state.messages)
        response = await self._call_llm_with_fallback(state.messages, self._make_stream_cb())
        if response is None:
            return None
        self._consecutive_failures = 0
        input_tok, output_tok = self._track_usage(response, state.session_id)
        state.total_input_tokens += input_tok
        state.total_output_tokens += output_tok
        self.total_tokens_used = state.total_input_tokens + state.total_output_tokens
        if self._check_token_budget():
            return None
        output_items = _extract_output_items(response)
        assistant_msg = self._build_assistant_msg(output_items)
        state.messages.append(assistant_msg)
        state.message_history.append(assistant_msg)
        state.messages = self._enforce_context_window(state.messages)
        action = self.decision_engine.decide(output_items)
        if action.type == ActionType.RESPOND:
            return self._handle_respond(action, task, state)
        if action.type == ActionType.CALL_TOOL:
            await self._handle_tool_calls(action, output_items, state, task, assistant_msg, response, input_tok, output_tok)
        elif action.type == ActionType.ERROR:
            self.error, self.status, self._running = action.reasoning, f"error: {action.reasoning}", False
        elif action.type == ActionType.LOOP_END:
            self._running = False
        return None

    def _save_training_data(self, data_collector: Any) -> None:
        """Save training data collector."""
        try:
            self._data_collector = data_collector
            data_collector.save()
        except Exception:
            _log.warning("Failed to save training data collector", exc_info=True)

    def _save_session_memory(self, task: str) -> None:
        """Save session summary to memory system."""
        success = not self.error and "error" not in (self.status or "").lower()
        duration_sec = int(time.time() - self.start_time) if self.start_time else 0
        tools_used = [d["tool"] for d in self._key_decisions]
        tool_summary = ", ".join(tools_used) if tools_used else "none"
        failed_tools = [d["tool"] for d in self._key_decisions if not d.get("success")]
        memory_content = self._build_memory_content(task, success, duration_sec, tool_summary)
        importance = self._calc_memory_importance()
        self.memory_mgr.remember(memory_content, importance=importance,
                                  tags=["session", "outcome", "success" if success else "failure"],
                                  title=f"Task: {task[:50]}")
        self._record_failed_tools(task, failed_tools)
        self.memory_mgr.end_session(promote_important=True)

    def _build_memory_content(self, task: str, success: bool, duration_sec: int, tool_summary: str) -> str:
        """Build memory content string from session data."""
        content = (f"Task: {task[:200]}\nResult: {'success' if success else 'failure'}\n"
                   f"Iterations: {self._iteration}, Duration: {duration_sec}s\nTools used: {tool_summary}")
        if self.error:
            content += f"\nError: {self.error[:200]}"
        return content

    def _calc_memory_importance(self) -> float:
        """Calculate memory importance based on session outcome."""
        if self.error:
            return 0.7
        return 0.6 if self._iteration > 10 else 0.5

    def _record_failed_tools(self, task: str, failed_tools: list) -> None:
        """Record failed tools to memory for learning."""
        if not failed_tools:
            return
        self.memory_mgr.learn(f"Tools that failed during task '{task[:100]}': {', '.join(failed_tools)}",
                               tags=["tool_failure", "learning"],
                               title=f"Tool failures: {', '.join(failed_tools)}", importance=0.6)

    def _finalize_run(self, task: str, data_collector: Any) -> None:
        """Finalize run: save data, update session, save memory."""
        self._save_training_data(data_collector)
        self._current_session.status = "error" if self.error else "completed"
        self.session_mgr.update_session(self._current_session)
        self.status = self.status or "finished"
        if self.memory_mgr and self.config.auto_remember:
            try:
                self._save_session_memory(task)
            except Exception as mem_err:
                self._notify("memory_error", {"error": str(mem_err)})


# ─── Main Loop Engine ────────────────────────────────────────────────────

class CodexLoop(_CodexLoopHelpers):
    """
    The main loop: task -> LLM -> decide -> execute -> repeat -> respond.
    Runs fully autonomously.
    """

    def __init__(self, config: Optional[LoopConfig] = None):
        self.config = config or LoopConfig()
        self.executor = get_executor()
        self.session_mgr = get_manager()
        self.decision_engine = DecisionEngine(self.executor, self.config)
        self._running = False
        self._current_session: Optional[Session] = None
        self._iteration = 0
        self._last_save = time.time()
        self._key_decisions: List[Dict[str, Any]] = []
        self._listeners: List[Callable] = []
        self.memory_mgr: Optional[MemoryManager] = None
        if self.config.enable_memory:
            self.memory_mgr = get_memory_manager()
        self.status = "idle"
        self.current_task = ""
        self.iteration_count = 0
        self.total_tokens_used = 0
        self.start_time: Optional[float] = None
        self.error: Optional[str] = None
        self._consecutive_failures = 0
        self._fallback_index = 0
        self._model_switch_history: List[Dict[str, str]] = []

    async def switch_model(self, model_name: str, provider: str = "") -> Dict[str, Any]:
        """Switch to a different model at runtime."""
        old_model = self.config.model
        old_provider = self.config.provider
        if model_name == old_model and (not provider or provider == old_provider):
            return {"success": True, "old_model": old_model, "new_model": old_model,
                    "error": "", "note": "already using this model"}
        new_provider = provider or _infer_provider(model_name)
        try:
            ok = await _verify_model(model_name, new_provider)
        except Exception as e:
            return {"success": False, "old_model": old_model, "new_model": model_name,
                    "error": f"verification failed: {e}"}
        if not ok:
            return {"success": False, "old_model": old_model, "new_model": model_name,
                    "error": "model verification returned empty response"}
        self.config.model = model_name
        self.config.provider = new_provider
        self._consecutive_failures = 0
        record = {"from": old_model, "from_provider": old_provider, "to": model_name,
                  "to_provider": new_provider, "reason": "manual", "timestamp": time.time()}
        self._model_switch_history.append(record)
        self._notify("model_switched", record)
        return {"success": True, "old_model": old_model, "new_model": model_name, "error": ""}

    def _try_fallback(self) -> Optional[str]:
        """Attempt to switch to the next fallback model."""
        fallbacks = self.config.fallback_models
        if not fallbacks or self._fallback_index >= len(fallbacks):
            return None
        new_model = fallbacks[self._fallback_index]
        self._fallback_index += 1
        old_model = self.config.model
        new_provider = _infer_provider(new_model)
        self.config.model = new_model
        self.config.provider = new_provider
        self._consecutive_failures = 0
        record = {"from": old_model, "to": new_model, "to_provider": new_provider,
                  "reason": "auto_fallback", "timestamp": time.time()}
        self._model_switch_history.append(record)
        self._notify("model_fallback", record)
        return new_model

    def get_model_switch_history(self) -> List[Dict[str, str]]:
        return list(self._model_switch_history)

    def add_listener(self, cb: Callable):
        self._listeners.append(cb)

    def _notify(self, msg: str, data: Optional[Dict] = None):
        for cb in self._listeners:
            try:
                cb(msg, data or {})
            except Exception:
                _log.warning("Listener callback %s failed for msg=%s", cb, msg, exc_info=True)

    async def run_task(self, task: str, session_id: Optional[str] = None,
                       timeout_sec: Optional[float] = None) -> str:
        """Run a task autonomously through the LLM loop."""
        self._running = True
        self.status = "running"
        self.current_task = task
        self._iteration = 0
        self.start_time = time.time()
        self.error = None
        self._key_decisions = []
        state = self._init_run(task, session_id)
        try:
            while self._running and self._iteration < self.config.max_iterations:
                result = await self._run_iteration(task, state)
                if result is not None:
                    return result
            if self._iteration >= self.config.max_iterations:
                self.status = f"max_iterations_reached ({self._iteration})"
                self.error = f"Max iterations ({self.config.max_iterations}) reached"
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self.status = f"error: {self.error}"
            traceback.print_exc()
        finally:
            self._finalize_run(task, state.data_collector)
        return f"Loop ended: {self.status} | Error: {self.error or 'none'}"

    def stop(self):
        self._running = False
        self.status = "stopped"

    def get_status(self) -> Dict[str, Any]:
        duration = time.time() - self.start_time if self.start_time else 0
        return {
            "status": self.status, "task": self.current_task,
            "iteration": self._iteration, "total_tokens": self.total_tokens_used,
            "duration_sec": int(duration), "error": self.error,
            "session_id": self._current_session.id if self._current_session else None,
        }


# ─── Cost Estimation ───────────────────────────────────────────────────────

COST_PER_1K = {
    "deepseek": (0.001, 0.003),
    "xiaomi": (0.001, 0.003),
    "ollama": (0, 0),
    "anthropic": (0.003, 0.015),
}


def _estimate_cost(input_tok: int, output_tok: int, provider: str) -> float:
    rates = COST_PER_1K.get(provider, (0, 0))
    return (input_tok / 1000 * rates[0]) + (output_tok / 1000 * rates[1])


# ─── Convenience Runner ──────────────────────────────────────────────────

async def run_automated(task: str, **config_kwargs) -> str:
    """One-liner to run a task fully automatically."""
    config = LoopConfig(**config_kwargs)
    loop = CodexLoop(config)
    return await loop.run_task(task)


# ─── Enhanced Codex Loop ──────────────────────────────────────────────────

_REASONING_PROMPTS = {
    1: "Analyze this task in detail. Consider:\n1. What exactly needs to be done?\n"
       "2. What are the key components and requirements?\n3. What tools or resources are needed?\n"
       "4. What are potential challenges?\n5. What is the best approach?\n\nTask: {task}\n\nProvide a detailed analysis.",
    2: "Based on the analysis, create a detailed execution plan.\n\nPrevious Analysis:\n{context}\n\n"
       "Task: {task}\n\nCreate a clear, actionable plan with:\n1. Specific steps in order\n"
       "2. Tools needed for each step\n3. Expected outcomes\n4. Potential risks and mitigations",
}


def _get_reasoning_prompt(round_num: int, task: str, context: str) -> str:
    """Get the reasoning prompt for a given round."""
    if round_num in _REASONING_PROMPTS:
        return _REASONING_PROMPTS[round_num].format(task=task, context=context)
    return (f"Review the plan and refine the execution strategy.\n\nPrevious Analysis and Plan:\n{context}\n\n"
            f"Task: {task}\n\nIdentify:\n1. Any gaps or missing steps\n2. Potential improvements\n"
            f"3. Risk mitigation strategies\n4. Final execution strategy")


class EnhancedCodexLoop(CodexLoop):
    """
    Enhanced CodexLoop with multi-round reasoning capabilities.
    Features: Chain-of-Thought prompting, multi-round reasoning, self-validation.
    """

    def __init__(self, config: Optional[LoopConfig] = None):
        super().__init__(config)
        self.reasoning_history: List[Dict[str, str]] = []

    async def run_task(self, task: str, session_id: Optional[str] = None,
                       timeout_sec: Optional[float] = None) -> str:
        """Run task with optional multi-round reasoning."""
        if not self.config.enable_multi_round_reasoning:
            return await super().run_task(task, session_id, timeout_sec)
        self._notify("reasoning_start", {"task": task, "rounds": self.config.reasoning_rounds})
        reasoning_context = await self._multi_round_reason(task)
        self._notify("reasoning_complete", {"task": task, "thoughts": len(self.reasoning_history)})
        enhanced_task = self._build_enhanced_task(task, reasoning_context)
        original_prompt = self.config.system_prompt
        if self.config.chain_of_thought:
            self.config.system_prompt = CHAIN_OF_THOUGHT_PROMPT + "\n\n" + original_prompt
        try:
            result = await super().run_task(enhanced_task, session_id, timeout_sec)
        finally:
            self.config.system_prompt = original_prompt
        return result

    async def _multi_round_reason(self, task: str) -> str:
        """Run multiple rounds of reasoning on the task."""
        self.reasoning_history = []
        context = ""
        for round_num in range(1, self.config.reasoning_rounds + 1):
            self._notify("reasoning_round", {"round": round_num, "total": self.config.reasoning_rounds})
            prompt = _get_reasoning_prompt(round_num, task, context)
            reasoning_result = await self._call_reasoning_llm(prompt)
            self.reasoning_history.append({"round": round_num, "prompt": prompt[:200] + "...", "result": reasoning_result})
            context += f"\n\nRound {round_num}:\n{reasoning_result}"
        return context

    async def _call_reasoning_llm(self, prompt: str) -> str:
        """Call LLM for reasoning (separate from tool execution)."""
        messages = [
            {"role": "system", "content": "You are an expert problem solver. Think carefully and provide detailed analysis."},
            {"role": "user", "content": prompt},
        ]
        config = LoopConfig(temperature=self.config.reasoning_temperature,
                            max_output_tokens=self.config.max_output_tokens,
                            model=self.config.model, provider=self.config.provider)
        try:
            response = await _call_llm_async(messages, config,
                                              os.environ.get("CODEX_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "",
                                              config.provider, config.model)
            output = response.get("output", [])
            text = next((c.get("text", "") for item in output if item.get("type") == "message"
                          for c in item.get("content", []) if isinstance(c, dict) and c.get("type") == "output_text"), None)
            return text if text is not None else "No reasoning output"
        except Exception as e:
            return f"Reasoning error: {str(e)}"

    def _build_enhanced_task(self, task: str, reasoning_context: str) -> str:
        return (f"Task: {task}\n\nReasoning Context:\n{reasoning_context}\n\n"
                f"Based on the above analysis and planning, execute this task. Use the tools available to complete each step.")

    def get_reasoning_history(self) -> List[Dict[str, str]]:
        return self.reasoning_history


# ─── Quick Enhanced Runner ────────────────────────────────────────────────

async def run_enhanced(task: str, reasoning_rounds: int = 3, **config_kwargs) -> str:
    """Run task with multi-round reasoning."""
    config = LoopConfig(enable_multi_round_reasoning=True, reasoning_rounds=reasoning_rounds,
                        chain_of_thought=True, **config_kwargs)
    loop = EnhancedCodexLoop(config)
    return await loop.run_task(task)


if __name__ == "__main__":
    async def test():
        print("=== Standard Mode ===")
        result = await run_automated("Write a hello world Python file at D:/codex-local/test_hello.py")
        print(result)
        print("\n=== Enhanced Mode (Multi-Round Reasoning) ===")
        result = await run_enhanced("Create a Python function that calculates fibonacci numbers with memoization", reasoning_rounds=2)
        print(result)

    asyncio.run(test())
