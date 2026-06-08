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
    max_total_tokens: int = 50000  # Total token budget for a single run_task()
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


# ─── Main Loop Engine ────────────────────────────────────────────────────

class CodexLoop:
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
        self._key_decisions: List[Dict[str, Any]] = []  # Track tool calls for memory
        self._listeners: List[Callable] = []

        # Memory system
        self.memory_mgr: Optional[MemoryManager] = None
        if self.config.enable_memory:
            self.memory_mgr = get_memory_manager()

        self.status = "idle"
        self.current_task = ""
        self.iteration_count = 0
        self.total_tokens_used = 0
        self.start_time: Optional[float] = None
        self.error: Optional[str] = None

        # Model switching state
        self._consecutive_failures = 0
        self._fallback_index = 0  # index into fallback_models
        self._model_switch_history: List[Dict[str, str]] = []

    async def switch_model(self, model_name: str, provider: str = "") -> Dict[str, Any]:
        """Switch to a different model at runtime.

        Args:
            model_name: Target model name (e.g. "deepseek-chat", "gpt-4o")
            provider: Target provider (auto-inferred if empty)

        Returns:
            {success: bool, old_model: str, new_model: str, error: str}
        """
        old_model = self.config.model
        old_provider = self.config.provider

        if model_name == old_model and (not provider or provider == old_provider):
            return {"success": True, "old_model": old_model, "new_model": old_model,
                    "error": "", "note": "already using this model"}

        # Resolve provider
        new_provider = provider or _infer_provider(model_name)

        # Verify new model is reachable
        try:
            ok = await _verify_model(model_name, new_provider)
        except Exception as e:
            return {"success": False, "old_model": old_model, "new_model": model_name,
                    "error": f"verification failed: {e}"}

        if not ok:
            return {"success": False, "old_model": old_model, "new_model": model_name,
                    "error": "model verification returned empty response"}

        # Apply switch
        self.config.model = model_name
        self.config.provider = new_provider
        self._consecutive_failures = 0

        record = {
            "from": old_model,
            "from_provider": old_provider,
            "to": model_name,
            "to_provider": new_provider,
            "reason": "manual",
            "timestamp": time.time(),
        }
        self._model_switch_history.append(record)

        self._notify("model_switched", record)
        return {"success": True, "old_model": old_model, "new_model": model_name, "error": ""}

    def _try_fallback(self) -> Optional[str]:
        """Attempt to switch to the next fallback model.

        Returns:
            New model name if switched, None if no more fallbacks.
        """
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

        record = {
            "from": old_model,
            "to": new_model,
            "to_provider": new_provider,
            "reason": "auto_fallback",
            "timestamp": time.time(),
        }
        self._model_switch_history.append(record)
        self._notify("model_fallback", record)
        return new_model

    def get_model_switch_history(self) -> List[Dict[str, str]]:
        """Return the history of model switches in this session."""
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
        self._running = True
        self.status = "running"
        self.current_task = task
        self._iteration = 0
        self.start_time = time.time()
        self.error = None
        self._key_decisions = []

        # Smart routing: automatically select the optimal model
        if self.config.enable_smart_routing:
            from runtime.smart_router import get_router
            router = get_router(
                monthly_budget=self.config.monthly_budget,
                prefer_local=self.config.prefer_local,
            )
            routing_result = router.route(
                task=task,
                require_tools=True,  # CodexLoop needs tool support
                quality_threshold=self.config.quality_threshold,
            )

            # Update config with routed model
            self.config.model = routing_result["model_config"].model
            self.config.provider = routing_result["model_config"].provider

            self._notify("routing", {
                "complexity": routing_result["complexity"].value,
                "model": routing_result["model_key"],
                "reason": routing_result["reason"],
                "estimated_cost": routing_result["estimated_cost"],
            })

        if session_id:
            self._current_session = self.session_mgr.get_session(session_id)
        if not self._current_session:
            self._current_session = self.session_mgr.create_session(
                model=self.config.model,
                provider=self.config.provider,
                metadata={"task": task},
            )

        session_id = self._current_session.id

        # Initialize memory for this session
        if self.memory_mgr:
            self.memory_mgr.set_session(session_id)
            # Store task in working memory
            self.memory_mgr.store(
                f"Task: {task}",
                importance=0.8,
                tags=["task", "current"],
                source="user"
            )

        # Build messages with memory context injection
        system_prompt = self.config.system_prompt
        if self.memory_mgr and self.config.memory_context_max > 0:
            memory_context = self.memory_mgr.get_relevant_memories_for_task(
                task, max_memories=self.config.memory_context_max
            )
            if memory_context:
                system_prompt = f"{system_prompt}\n\n{memory_context}"

        messages = _build_messages(task, [], system_prompt,
                                     max_context_tokens=self.config.max_context_tokens)
        message_history: List[Dict] = []
        total_input_tokens = 0

        # Initialize data collector for training data
        data_collector = DataCollector(session_id=session_id)
        total_output_tokens = 0

        try:
            while self._running and self._iteration < self.config.max_iterations:
                self._iteration += 1
                self.iteration_count = self._iteration
                self.status = f"iterating ({self._iteration})"
                self._notify("iteration", {
                    "iteration": self._iteration,
                    "session_id": session_id,
                    "action": "calling_llm",
                })

                # Build stream callback if streaming is enabled
                _stream_cb = None
                if self.config.stream:
                    def _stream_cb(chunk: str):
                        self._notify("stream_chunk", {
                            "iteration": self._iteration,
                            "chunk": chunk,
                        })

                try:
                    response = await _call_llm_async(
                        messages, self.config,
                        _resolve_api_key(),
                        self.config.provider,
                        self.config.model,
                        stream_callback=_stream_cb,
                    )
                except Exception as llm_err:
                    self._consecutive_failures += 1
                    # Auto-fallback when consecutive failures reach threshold
                    if (self.config.fallback_models
                            and self._consecutive_failures >= self.config.fallback_threshold):
                        new_model = self._try_fallback()
                        if new_model:
                            self._notify("auto_fallback", {
                                "new_model": new_model,
                                "consecutive_failures": self._consecutive_failures,
                                "error": str(llm_err)[:200],
                            })
                            # Retry with the new model
                            response = await _call_llm_async(
                                messages, self.config,
                                _resolve_api_key(),
                                self.config.provider,
                                self.config.model,
                                stream_callback=_stream_cb,
                            )
                        else:
                            # No more fallbacks -- set error and break
                            self.error = f"All models failed: {llm_err}"
                            self.status = "error: all models failed"
                            self._running = False
                            break
                    else:
                        # Below threshold -- log and continue to next iteration
                        self._notify("llm_failure", {
                            "consecutive_failures": self._consecutive_failures,
                            "threshold": self.config.fallback_threshold,
                            "error": str(llm_err)[:200],
                        })
                        continue

                # Success -- reset consecutive failure counter
                self._consecutive_failures = 0

                usage = response.get("usage", {})
                input_tok = usage.get("input_tokens", 0)
                output_tok = usage.get("completion_tokens", 0)
                total_input_tokens += input_tok
                total_output_tokens += output_tok
                self.total_tokens_used = total_input_tokens + total_output_tokens

                # Token budget check
                if self.config.max_total_tokens > 0 and self.total_tokens_used >= self.config.max_total_tokens:
                    self.error = f"token_budget_exceeded ({self.total_tokens_used}/{self.config.max_total_tokens})"
                    self.status = "token_budget_exceeded"
                    self._running = False
                    self._notify("token_budget_exceeded", {
                        "total_tokens": self.total_tokens_used,
                        "budget": self.config.max_total_tokens,
                        "iteration": self._iteration,
                    })
                    break

                self.session_mgr.update_tokens(
                    session_id, input_tok, output_tok,
                    cost=_estimate_cost(input_tok, output_tok, self.config.provider),
                )

                output_items = _extract_output_items(response)

                # Build assistant message with content AND tool_calls
                assistant_msg = {"role": "assistant", "content": ""}
                has_tool_calls = any(item.get("type") == "function_call" for item in output_items)
                if has_tool_calls:
                    tool_calls_out = []
                    for item in output_items:
                        if item.get("type") == "function_call":
                            cid = item.get("call_id") or f"auto_{id(item)}"
                            tool_calls_out.append({
                                "id": cid,
                                "type": "function",
                                "function": {
                                    "name": item.get("name", ""),
                                    "arguments": item.get("arguments", "{}"),
                                }
                            })
                    assistant_msg["tool_calls"] = tool_calls_out
                    assistant_msg["content"] = ""

                # CRITICAL: append assistant message THEN tool result to messages so LLM sees the pairing
                messages.append(assistant_msg)
                message_history.append(assistant_msg)

                # Enforce context window limit: truncate oldest messages when exceeding threshold
                if len(messages) > 2:  # At least system + 1 message
                    if self.config.max_context_tokens > 0:
                        max_chars = self.config.max_context_tokens * 4
                    else:
                        max_chars = MAX_MESSAGES_CHARS
                    total_chars = sum(_msg_char_len(m) for m in messages)
                    if total_chars > max_chars:
                        system_msg = messages[0]
                        recent_msgs = messages[1:]
                        while recent_msgs and total_chars > max_chars:
                            removed = recent_msgs.pop(0)
                            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                                if recent_msgs and recent_msgs[0].get("role") == "tool":
                                    recent_msgs.pop(0)
                            total_chars = _msg_char_len(system_msg) + \
                                sum(_msg_char_len(m) for m in recent_msgs)

                        while recent_msgs and recent_msgs[0].get("role") == "tool":
                            recent_msgs.pop(0)
                            total_chars = _msg_char_len(system_msg) + \
                                sum(_msg_char_len(m) for m in recent_msgs)

                        messages = [system_msg] + recent_msgs

                action = self.decision_engine.decide(output_items)

                if action.type == ActionType.RESPOND:
                    if not action.will_continue:
                        # Record final response as training data
                        try:
                            data_collector.record(
                                task=task,
                                messages_sent=messages,
                                llm_response=response,
                                tool_calls=[],
                                tool_results=[],
                                success=True,
                                tokens_used=input_tok + output_tok,
                                iteration=self._iteration,
                            )
                        except Exception:
                            _log.warning("Failed to record final response training data", exc_info=True)
                        self.status = "completed"
                        self._running = False
                        final_text = action.response_text or ""
                        self._current_session.status = "completed"
                        self.session_mgr.update_session(self._current_session)
                        return final_text
                    # will_continue=True: suppress the text and continue looping
                    continue

                elif action.type == ActionType.CALL_TOOL:
                    # Find the call_id for this tool call from output_items
                    call_id = None
                    for item in output_items:
                        if item.get("type") == "function_call" and item.get("name") == action.tool_name:
                            call_id = item.get("call_id")
                            break
                    if not call_id:
                        call_id = f"auto_{id(action)}"
                    self._notify("iteration", {
                        "iteration": self._iteration,
                        "session_id": session_id,
                        "action": "executing_tool",
                        "tool": action.tool_name,
                        "args": action.tool_args,
                    })
                    result = self.decision_engine.execute_action(action)

                    result_str = json.dumps(result, ensure_ascii=False, default=str)
                    tool_result_msg = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result_str,
                    }
                    messages.append(tool_result_msg)
                    message_history.append(tool_result_msg)
                    self.session_mgr.append_message(session_id, tool_result_msg)
                    self.session_mgr.append_tool_result(session_id, {
                        "iteration": self._iteration,
                        "tool": action.tool_name,
                        "args": action.tool_args,
                        "success": result.get("success") if isinstance(result, dict) else False,
                        "timestamp": int(time.time()),
                    })

                    # Track key decisions for memory
                    self._key_decisions.append({
                        "iteration": self._iteration,
                        "tool": action.tool_name,
                        "success": result.get("success") if isinstance(result, dict) else False,
                    })

                    # Memory: Store important tool results
                    if self.memory_mgr and self.config.auto_remember:
                        try:
                            success = result.get("success") if isinstance(result, dict) else False
                            # Remember errors for learning
                            if not success and isinstance(result, dict):
                                error_msg = result.get("error", "")
                                if error_msg:
                                    self.memory_mgr.store(
                                        f"Tool error ({action.tool_name}): {error_msg}",
                                        importance=0.7,
                                        tags=["error", action.tool_name],
                                        source="tool_execution"
                                    )
                            # Remember successful file operations
                            elif success and action.tool_name in ("write_file", "edit_file", "create_directory"):
                                file_path = action.tool_args.get("path", "") if action.tool_args else ""
                                if file_path:
                                    self.memory_mgr.store(
                                        f"Modified file: {file_path}",
                                        importance=0.5,
                                        tags=["file", "modified", action.tool_name],
                                        source="tool_execution"
                                    )
                        except Exception:
                            _log.warning("Failed to store tool execution in memory", exc_info=True)

                    # Execute remaining pending calls from same LLM response
                    pending = getattr(self.decision_engine, '_pending_calls', [])
                    while pending:
                        next_call_id, next_tool_name, next_tool_args = pending.pop(0)
                        self._notify("iteration", {
                            "iteration": self._iteration,
                            "session_id": session_id,
                            "action": "executing_tool",
                            "tool": next_tool_name,
                            "args": next_tool_args,
                        })
                        next_result = self.decision_engine.execute_action(
                            Action(type=ActionType.CALL_TOOL, tool_name=next_tool_name, tool_args=next_tool_args)
                        )
                        next_result_str = json.dumps(next_result, ensure_ascii=False, default=str)
                        next_tool_msg = {
                            "role": "tool",
                            "tool_call_id": next_call_id,
                            "content": next_result_str,
                        }
                        messages.append(next_tool_msg)
                        message_history.append(next_tool_msg)
                        self.session_mgr.append_tool_result(session_id, {
                            "iteration": self._iteration,
                            "tool": next_tool_name,
                            "args": next_tool_args,
                            "success": next_result.get("success") if isinstance(next_result, dict) else False,
                            "timestamp": int(time.time()),
                        })
                        # Clear pending so execute_action doesn't see stale state
                        self.decision_engine._pending_calls = pending

                    # Record training data for this iteration
                    try:
                        tc_list = assistant_msg.get("tool_calls", [])
                        tool_results_for_record = []
                        for msg in messages:
                            if msg.get("role") == "tool":
                                tool_results_for_record.append({
                                    "tool_call_id": msg.get("tool_call_id", ""),
                                    "content": msg.get("content", ""),
                                    "success": True,  # will be updated below
                                })
                        success_flag = result.get("success") if isinstance(result, dict) else False
                        data_collector.record(
                            task=task,
                            messages_sent=messages[:-1],  # exclude the tool result we just added
                            llm_response=response,
                            tool_calls=tc_list,
                            tool_results=tool_results_for_record,
                            success=success_flag,
                            tokens_used=input_tok + output_tok,
                            iteration=self._iteration,
                        )
                    except Exception:
                        _log.warning("Failed to collect training data for iteration %d", self._iteration, exc_info=True)

                    if time.time() - self._last_save > self.config.auto_save_interval_sec:
                        self.session_mgr.checkpoint(self._current_session)
                        self._last_save = time.time()
                        self._notify("checkpoint", {"session_id": session_id})

                elif action.type == ActionType.ERROR:
                    self.error = action.reasoning
                    self.status = f"error: {action.reasoning}"
                    self._running = False
                    break

                elif action.type == ActionType.LOOP_END:
                    self._running = False
                    break

            if self._iteration >= self.config.max_iterations:
                self.status = f"max_iterations_reached ({self._iteration})"
                self.error = f"Max iterations ({self.config.max_iterations}) reached"

        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self.status = f"error: {self.error}"
            traceback.print_exc()

        finally:
            # Save training data
            try:
                self._data_collector = data_collector
                data_collector.save()
            except Exception:
                _log.warning("Failed to save training data collector", exc_info=True)

            self._current_session.status = "error" if self.error else "completed"
            self.session_mgr.update_session(self._current_session)
            self.status = self.status or "finished"

            # Memory system: save session summary with key_decisions and end session
            if self.memory_mgr and self.config.auto_remember:
                try:
                    success = not self.error and "error" not in (self.status or "").lower()
                    duration_sec = int(time.time() - self.start_time) if self.start_time else 0

                    # Build task summary for memory
                    task_summary = {
                        "task": task,
                        "success": success,
                        "status": self.status,
                        "iterations": self._iteration,
                        "duration_sec": duration_sec,
                        "error": self.error,
                    }

                    # Summarize key decisions (tool calls made)
                    tools_used = [d["tool"] for d in self._key_decisions]
                    tool_summary = ", ".join(tools_used) if tools_used else "none"
                    failed_tools = [d["tool"] for d in self._key_decisions if not d.get("success")]
                    key_decisions_summary = {
                        "tools_called": tools_used,
                        "total_tool_calls": len(self._key_decisions),
                        "failed_tools": failed_tools,
                    }

                    # Build memory content
                    memory_content = (
                        f"Task: {task[:200]}\n"
                        f"Result: {'success' if success else 'failure'}\n"
                        f"Iterations: {self._iteration}, Duration: {duration_sec}s\n"
                        f"Tools used: {tool_summary}"
                    )
                    if self.error:
                        memory_content += f"\nError: {self.error[:200]}"

                    # Determine importance based on outcome
                    importance = 0.5
                    if self.error:
                        importance = 0.7  # Errors are worth remembering
                    elif self._iteration > 10:
                        importance = 0.6  # Complex tasks

                    # Store as episodic memory with structured metadata
                    self.memory_mgr.remember(
                        memory_content,
                        importance=importance,
                        tags=["session", "outcome", "success" if success else "failure"],
                        title=f"Task: {task[:50]}"
                    )

                    # Also learn from failures as semantic knowledge
                    if failed_tools:
                        self.memory_mgr.learn(
                            f"Tools that failed during task '{task[:100]}': {', '.join(failed_tools)}",
                            tags=["tool_failure", "learning"],
                            title=f"Tool failures: {', '.join(failed_tools)}",
                            importance=0.6,
                        )

                    # End session and promote important working memories
                    self.memory_mgr.end_session(promote_important=True)

                except Exception as mem_err:
                    # Don't let memory errors break the main flow
                    self._notify("memory_error", {"error": str(mem_err)})

        return f"Loop ended: {self.status} | Error: {self.error or 'none'}"

    def stop(self):
        self._running = False
        self.status = "stopped"

    def get_status(self) -> Dict[str, Any]:
        duration = time.time() - self.start_time if self.start_time else 0
        return {
            "status": self.status,
            "task": self.current_task,
            "iteration": self._iteration,
            "total_tokens": self.total_tokens_used,
            "duration_sec": int(duration),
            "error": self.error,
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
    """
    One-liner to run a task fully automatically.
    """
    config = LoopConfig(**config_kwargs)
    loop = CodexLoop(config)
    return await loop.run_task(task)


# ─── Enhanced Codex Loop ──────────────────────────────────────────────────

class EnhancedCodexLoop(CodexLoop):
    """
    Enhanced CodexLoop with multi-round reasoning capabilities.

    Features:
    - Chain-of-Thought prompting
    - Multi-round reasoning for complex tasks
    - Better handling of ambiguous requirements
    - Self-validation of approach before execution
    """

    def __init__(self, config: Optional[LoopConfig] = None):
        super().__init__(config)
        self.reasoning_history: List[Dict[str, str]] = []

    async def run_task(self, task: str, session_id: Optional[str] = None,
                       timeout_sec: Optional[float] = None) -> str:
        """Run task with optional multi-round reasoning"""

        if not self.config.enable_multi_round_reasoning:
            # Use standard loop
            return await super().run_task(task, session_id, timeout_sec)

        # Phase 1: Multi-round reasoning
        self._notify("reasoning_start", {"task": task, "rounds": self.config.reasoning_rounds})

        reasoning_context = await self._multi_round_reason(task)

        self._notify("reasoning_complete", {
            "task": task,
            "thoughts": len(self.reasoning_history),
        })

        # Phase 2: Execute with enhanced context
        enhanced_task = self._build_enhanced_task(task, reasoning_context)

        # Use Chain-of-Thought system prompt if enabled
        original_prompt = self.config.system_prompt
        if self.config.chain_of_thought:
            self.config.system_prompt = CHAIN_OF_THOUGHT_PROMPT + "\n\n" + original_prompt

        try:
            result = await super().run_task(enhanced_task, session_id, timeout_sec)
        finally:
            self.config.system_prompt = original_prompt

        return result

    async def _multi_round_reason(self, task: str) -> str:
        """Run multiple rounds of reasoning on the task"""
        self.reasoning_history = []
        context = ""

        for round_num in range(1, self.config.reasoning_rounds + 1):
            self._notify("reasoning_round", {"round": round_num, "total": self.config.reasoning_rounds})

            # Build reasoning prompt
            if round_num == 1:
                prompt = f"""Analyze this task in detail. Consider:
1. What exactly needs to be done?
2. What are the key components and requirements?
3. What tools or resources are needed?
4. What are potential challenges?
5. What is the best approach?

Task: {task}

Provide a detailed analysis."""

            elif round_num == 2:
                prompt = f"""Based on the analysis, create a detailed execution plan.

Previous Analysis:
{context}

Task: {task}

Create a clear, actionable plan with:
1. Specific steps in order
2. Tools needed for each step
3. Expected outcomes
4. Potential risks and mitigations"""

            else:
                prompt = f"""Review the plan and refine the execution strategy.

Previous Analysis and Plan:
{context}

Task: {task}

Identify:
1. Any gaps or missing steps
2. Potential improvements
3. Risk mitigation strategies
4. Final execution strategy"""

            # Call LLM for reasoning
            reasoning_result = await self._call_reasoning_llm(prompt)

            self.reasoning_history.append({
                "round": round_num,
                "prompt": prompt[:200] + "...",
                "result": reasoning_result,
            })

            context += f"\n\nRound {round_num}:\n{reasoning_result}"

        return context

    async def _call_reasoning_llm(self, prompt: str) -> str:
        """Call LLM for reasoning (separate from tool execution)"""
        messages = [
            {"role": "system", "content": "You are an expert problem solver. Think carefully and provide detailed analysis."},
            {"role": "user", "content": prompt},
        ]

        # Use lower temperature for reasoning
        config = LoopConfig(
            temperature=self.config.reasoning_temperature,
            max_output_tokens=self.config.max_output_tokens,
            model=self.config.model,
            provider=self.config.provider,
        )

        try:
            response = await _call_llm_async(
                messages, config,
                os.environ.get("CODEX_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "",
                config.provider,
                config.model,
            )

            # Extract text from response
            output = response.get("output", [])
            text = next(
                (c.get("text", "")
                 for item in output
                 if item.get("type") == "message"
                 for c in item.get("content", [])
                 if isinstance(c, dict) and c.get("type") == "output_text"),
                None,
            )
            return text if text is not None else "No reasoning output"

        except Exception as e:
            return f"Reasoning error: {str(e)}"

    def _build_enhanced_task(self, task: str, reasoning_context: str) -> str:
        """Build enhanced task with reasoning context"""
        return f"""Task: {task}

Reasoning Context:
{reasoning_context}

Based on the above analysis and planning, execute this task. Use the tools available to complete each step."""

    def get_reasoning_history(self) -> List[Dict[str, str]]:
        """Get the reasoning history"""
        return self.reasoning_history


# ─── Quick Enhanced Runner ────────────────────────────────────────────────

async def run_enhanced(task: str, reasoning_rounds: int = 3, **config_kwargs) -> str:
    """
    Run task with multi-round reasoning.

    Args:
        task: Task description
        reasoning_rounds: Number of reasoning rounds (default: 3)
        **config_kwargs: Additional LoopConfig arguments

    Returns:
        Task result
    """
    config = LoopConfig(
        enable_multi_round_reasoning=True,
        reasoning_rounds=reasoning_rounds,
        chain_of_thought=True,
        **config_kwargs,
    )
    loop = EnhancedCodexLoop(config)
    return await loop.run_task(task)


if __name__ == "__main__":
    async def test():
        # Test standard mode
        print("=== Standard Mode ===")
        result = await run_automated("Write a hello world Python file at D:/codex-local/test_hello.py")
        print(result)

        # Test enhanced mode
        print("\n=== Enhanced Mode (Multi-Round Reasoning) ===")
        result = await run_enhanced(
            "Create a Python function that calculates fibonacci numbers with memoization",
            reasoning_rounds=2,
        )
        print(result)

    asyncio.run(test())
