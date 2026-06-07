"""
Codex-Local Auto-Loop Engine
The core decision engine: receives LLM output, decides next action, executes automatically.
No human confirmation needed. Every action is logged and can be recovered.
"""

import os
import json
import time
import asyncio
import threading
import traceback
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

# CRITICAL: Unset proxy env vars to prevent API key mangling
for _k in ['HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(_k, None)

import sys as _sys
_root = Path(__file__).parent.parent
if str(_root) not in _sys.path:
    _sys.path.insert(0, str(_root))

from tools.executor import ToolExecutor, get_executor, TOOL_DEFINITIONS  # noqa: E402
from runtime.session import SessionManager, get_manager, Session  # noqa: E402
from runtime.memory import MemoryManager, get_memory_manager  # noqa: E402


# ─── Decision Types ─────────────────────────────────────────────────────────

class ActionType(Enum):
    CALL_TOOL = "call_tool"
    RESPOND = "respond"
    WAIT = "wait"
    LOOP_END = "loop_end"
    ERROR = "error"


@dataclass
class Action:
    type: ActionType
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    response_text: Optional[str] = None
    confidence: float = 1.0
    reasoning: str = ""
    will_continue: bool = True

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "response_text": self.response_text,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "will_continue": self.will_continue,
        }


# ─── System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an autonomous coding agent. You complete tasks by calling tools directly.

TOOL USAGE — use the RIGHT tool for each job:
- Read(file_path) — read a file
- Write(file_path, content) — CREATE a file. Use this for new files.
- Edit(file_path, old_string, new_string) — modify an existing file
- Bash(command) — RUN a command. Use this to execute scripts, run tests, verify output.
- sandbox_exec — ONLY for quick code snippets, NOT for file operations

IMPORTANT: sandbox_exec runs in an isolated directory. NEVER use it for tasks that create files.
Always use Write + Bash for file creation and execution.

WORKFLOW:
1. Read files to understand current state
2. Write or Edit to make changes
3. Bash to run/verify
4. If it fails, read the error, fix, retry once

RULES:
- Create files with Write, then run with Bash("python filename")
- Run tests with Bash("python -m pytest ...")
- Check output with Read or Bash
- Never describe what you would do — just do it
- Stop when the task is verified complete"""


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


# ─── LLM Interface ───────────────────────────────────────────────────────

def _convert_tools_to_openai_format(tools: List[Dict]) -> List[Dict]:
    """Convert flat tool format to OpenAI function format.
    Handles: {"type":"function","name":"Foo","parameters":{...}}
    And:    {"type":"function","function":{"name":"Foo","parameters":{...}}}"""
    converted = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        # If already has proper nested "function" key, pass through
        if "function" in t:
            converted.append(t)
        elif t.get("type") == "function":
            converted.append({
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                }
            })
        else:
            converted.append(t)
    return converted


MAX_MESSAGES_CHARS = 80_000  # ~20k tokens — keep request body under ~100KB

def _build_messages(task: str, history: List[Dict], system_prompt: str) -> List[Dict]:
    # Build full messages first
    full_messages = []
    for msg in history:
        role = msg.get("role", "user")
        m = {"role": role, "content": msg.get("content", "") or ""}
        if role == "tool" and msg.get("tool_call_id"):
            m["tool_call_id"] = msg["tool_call_id"]
        if role == "assistant" and msg.get("tool_calls"):
            m["tool_calls"] = msg["tool_calls"]
        full_messages.append(m)
    full_messages.append({"role": "user", "content": task})

    # Estimate total size
    total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in full_messages)

    if total_chars <= MAX_MESSAGES_CHARS:
        return [{"role": "system", "content": system_prompt}] + full_messages

    # Truncate oldest messages while preserving tool-call pairing integrity.
    # Strategy: keep system + most recent messages that fit.
    # We remove from the front, but always remove assistant+tool pairs together.
    recent = list(full_messages)  # copy
    while recent and total_chars > MAX_MESSAGES_CHARS:
        removed = recent.pop(0)
        # If we removed an assistant msg with tool_calls, also remove the following tool result(s)
        if removed.get("role") == "assistant" and removed.get("tool_calls"):
            while recent and recent[0].get("role") == "tool":
                recent.pop(0)
        # Recalculate
        total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in recent)

    # Final safety: drop orphaned tool results at the front
    while recent and recent[0].get("role") == "tool":
        recent.pop(0)

    return [{"role": "system", "content": system_prompt}] + recent


def _resolve_api_url(provider: str = "") -> str:
    """Resolve API base URL from provider name or env override."""
    # Check env override first (OPENAI_BASE_URL style)
    for var in ["CODEX_API_URL", "OPENAI_BASE_URL"]:
        url = os.environ.get(var)
        if url:
            return url.rstrip("/") + "/chat/completions"

    providers = {
        "deepseek": "https://api.deepseek.com/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "xiaomi": "https://api.xiaomi.com/v1/chat/completions",
        "ollama": "http://localhost:11434/v1/chat/completions",
    }
    if not provider:
        # Auto-detect: if OPENAI_BASE_URL is set, use openai
        if os.environ.get("OPENAI_BASE_URL"):
            return os.environ["OPENAI_BASE_URL"].rstrip("/") + "/chat/completions"
        return providers["deepseek"]
    return providers.get(provider, providers["deepseek"])


def _resolve_api_key() -> str:
    """Resolve API key from env, checking multiple sources."""
    for var in ["CODEX_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "XIAOMIMIMO_API_KEY"]:
        key = os.environ.get(var)
        if key:
            return key
    return ""


async def _call_llm_async(messages: List[Dict], config: LoopConfig,
                          api_key: str, provider: str, model: str) -> Dict[str, Any]:
    """Call the LLM directly via Chat Completions API with retry logic."""

    # Build Chat Completions body from message history
    chat_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            chat_messages.append({"role": "system", "content": content})
        elif role == "user":
            chat_messages.append({"role": "user", "content": content})
        elif role == "assistant":
            if msg.get("tool_calls"):
                # Assistant message with tool calls
                tool_calls = []
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    tool_calls.append({
                        "id": tc.get("id", f"call_{id(tc)}"),
                        "type": "function",
                        "function": {
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", "{}"),
                        }
                    })
                chat_messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
            else:
                chat_messages.append({"role": "assistant", "content": content or ""})
        elif role == "tool":
            # Tool result message
            chat_messages.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", "unknown"),
                "content": content,
            })

    # Only include tools if not a tool result message
    body = {
        "model": model,
        "messages": chat_messages,
        "stream": False,
        "temperature": config.temperature,
        "max_tokens": config.max_output_tokens,
    }
    # Always include tools so model can call them in every iteration
    # Use all tools — no filtering, API handles what it needs
    body["tools"] = _convert_tools_to_openai_format(TOOL_DEFINITIONS)

    # Call LLM directly with retry using requests session for reliability
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    api_url = _resolve_api_url(provider)
    adapter = HTTPAdapter(
        max_retries=Retry(total=10, backoff_factor=2.0, status_forcelist=[429, 500, 502, 503, 504]),
        pool_connections=1,
        pool_maxsize=1,
    )
    session.mount("https://", adapter)

    max_retries = 10
    base_delay = 3.0
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(
                api_url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + api_key,
                },
                timeout=(10, 120),  # (connect, read)
            )
            # Check HTTP status before attempting to parse JSON
            if resp.status_code != 200:
                err_body = resp.text or "no body"
                status = resp.status_code
                retryable = status in (429, 500, 502, 503, 504)
                if status == 400 and "context length" in err_body.lower():
                    raise RuntimeError(f"LLM API error {status}: {err_body}")
                if retryable and attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    import random
                    delay *= 0.75 + 0.5 * random.random()
                    last_exception = RuntimeError(f"LLM API error {status} (attempt {attempt}/{max_retries}): {err_body[:500]}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise RuntimeError(f"LLM API error {status}: {err_body[:1000]}")
            try:
                result = resp.json()
            except json.JSONDecodeError as e:
                raise RuntimeError(f"LLM API returned non-JSON response (status {resp.status_code}): {resp.text[:500]}") from e
            choices = result.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                error_msg = result.get("error", {}).get("message", "Empty choices in response")
                raise RuntimeError(f"LLM API returned invalid response: {error_msg}")
            return _convert_chat_to_response_format(result, model)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.RequestException) as e:
            # Network-level transient errors — retry with backoff
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                import random
                delay *= 0.75 + 0.5 * random.random()
                last_exception = RuntimeError(f"LLM API connection error (attempt {attempt}/{max_retries}): {e}")
                await asyncio.sleep(delay)
                continue
            else:
                raise RuntimeError(f"LLM API connection failed after {max_retries} retries: {e}") from e

    # If we exhausted retries, raise the last captured exception
    raise last_exception or RuntimeError("LLM API call failed after all retries")


def _convert_chat_to_response_format(chat_resp: Dict, model: str) -> Dict:
    """Convert Chat Completions response to internal response format."""
    import time, uuid
    choice = (chat_resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []

    output = []
    if content:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": content, "annotations": []}],
        })
    for tc in tool_calls:
        fn = tc.get("function") or {}
        output.append({
            "id": "fc_" + uuid.uuid4().hex,
            "type": "function_call",
            "status": "completed",
            "call_id": tc.get("id", ""),
            "name": fn.get("name", ""),
            "arguments": fn.get("arguments", "{}"),
        })

    usage = chat_resp.get("usage") or {}
    return {
        "id": "resp_" + uuid.uuid4().hex,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def _extract_output_items(response: Dict) -> List[Dict]:
    """Extract output items with validation and graceful fallback for malformed responses."""
    if not isinstance(response, dict):
        return []
    
    output = response.get("output")
    if output is None:
        # Try alternative response formats
        choices = response.get("choices")
        if choices and isinstance(choices, list) and len(choices) > 0:
            msg = choices[0].get("message", {})
            items = []
            content = msg.get("content", "")
            if content:
                items.append({
                    "id": "msg_fallback",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content, "annotations": []}],
                })
            for tc in msg.get("tool_calls", []):
                fn = tc.get("function", {})
                items.append({
                    "id": "fc_fallback_" + str(id(tc)),
                    "type": "function_call",
                    "status": "completed",
                    "call_id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", "{}"),
                })
            return items
        return []
    
    if not isinstance(output, list):
        return []
    
    # Validate each item and filter out malformed ones
    valid_items = []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "function_call":
            # Ensure function_call items have at minimum a name
            name = item.get("name", "")
            if name:
                valid_items.append(item)
            else:
                # Try to recover: check if there's a tool_name field
                tool_name = item.get("tool_name", item.get("function", {}).get("name", ""))
                if tool_name:
                    item["name"] = tool_name
                    valid_items.append(item)
        elif item_type == "message":
            content = item.get("content", [])
            if content and isinstance(content, list):
                valid_items.append(item)
            elif item.get("text"):  # Some models return flat text
                valid_items.append({
                    "id": item.get("id", "msg_recovered"),
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": item["text"], "annotations": []}],
                })
        else:
            # Unknown type — try to salvage if it has recognizable fields
            if item.get("name") and not item.get("type"):
                item["type"] = "function_call"
                valid_items.append(item)
            elif item.get("text") or item.get("content"):
                item["type"] = "message"
                valid_items.append(item)
    
    return valid_items


# ─── Auto-Decision Engine ─────────────────────────────────────────────────

class DecisionEngine:
    """
    Analyzes LLM output and decides what to do next.
    Maps function calls to real tool executions.
    """

    def __init__(self, executor: ToolExecutor, config: LoopConfig):
        self.executor = executor
        self.config = config

    def decide(self, output_items: List[Dict]) -> Action:
        if not output_items:
            return Action(
                type=ActionType.ERROR,
                reasoning="No output items from LLM",
                will_continue=False,
            )

        # Collect ALL function calls with their call_ids
        pending_calls = []
        for item in output_items:
            if item.get("type") == "function_call":
                tool_name = item.get("name", "")
                tool_args_str = item.get("arguments", "{}")
                if isinstance(tool_args_str, str):
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {"raw": tool_args_str}
                elif isinstance(tool_args_str, dict):
                    tool_args = tool_args_str
                else:
                    tool_args = {}
                call_id = item.get("call_id", f"call_{id(item)}")
                pending_calls.append((call_id, tool_name, tool_args))

        if pending_calls:
            # Return first call; store rest in config for batch execution
            call_id, tool_name, tool_args = pending_calls[0]
            self._pending_calls = pending_calls[1:]  # [(call_id, name, args), ...]
            return Action(
                type=ActionType.CALL_TOOL,
                tool_name=tool_name,
                tool_args=tool_args,
                confidence=0.95,
                reasoning=f"Calling tool: {tool_name}",
            )

        for item in output_items:
            item_type = item.get("type")

            if item_type == "message":
                content = item.get("content", [])
                text = ""
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "output_text":
                        text = c.get("text", "")
                        break

                if text:
                    # If text looks like a tool_call description rather than a real answer,
                    # treat it as needing another iteration
                    stripped = text.strip()
                    # Detect "describing instead of doing" patterns
                    describe_patterns = [
                        stripped.startswith("<"),
                        "tool_calls" in stripped,
                        "invoke name=" in stripped,
                        stripped.lower().startswith(("i'll ", "i will ", "let me ", "here's ", "first, ", "to fix")),
                        "```python" in stripped and len(stripped) > 200,
                        "i would " in stripped.lower() and "tool" in stripped.lower(),
                    ]
                    if any(describe_patterns):
                        # Model is describing tools in text instead of using tool_calls — force continue
                        self._suppressed_response = stripped
                        return Action(
                            type=ActionType.RESPOND,
                            response_text="[tool description suppressed — continuing]",
                            confidence=0.5,
                            reasoning="Model described tools in text, forcing next iteration",
                            will_continue=True,
                        )
                    return Action(
                        type=ActionType.RESPOND,
                        response_text=text,
                        confidence=1.0,
                        reasoning="Final response from LLM",
                        will_continue=False,
                    )

        return Action(
            type=ActionType.ERROR,
            reasoning="Could not understand LLM output format",
            will_continue=False,
        )

    def execute_action(self, action: Action) -> Dict[str, Any]:
        if action.type == ActionType.CALL_TOOL:
            tool_name = action.tool_name
            tool_args = action.tool_args or {}

            if tool_name.lower() in ("bash", "shell") and not self.config.trust_shell_commands:
                return {
                    "success": False,
                    "error": "Shell commands require confirmation (set trust_shell_commands=True)",
                    "blocked": True,
                }

            result = self.executor.execute_tool(tool_name, tool_args)
            return result

        elif action.type == ActionType.RESPOND:
            return {"success": True, "text": action.response_text}

        elif action.type == ActionType.ERROR:
            return {"success": False, "error": action.reasoning}

        return {"success": False, "error": "Unknown action type"}


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

    def add_listener(self, cb: Callable):
        self._listeners.append(cb)

    def _notify(self, msg: str, data: Optional[Dict] = None):
        for cb in self._listeners:
            try:
                cb(msg, data or {})
            except Exception:
                pass

    async def run_task(self, task: str, session_id: Optional[str] = None,
                       timeout_sec: Optional[float] = None) -> str:
        self._running = True
        self.status = "running"
        self.current_task = task
        self._iteration = 0
        self.start_time = time.time()
        self.error = None

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

        messages = _build_messages(task, [], system_prompt)
        message_history: List[Dict] = []
        total_input_tokens = 0
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

                response = await _call_llm_async(
                    messages, self.config,
                    _resolve_api_key(),
                    self.config.provider,
                    self.config.model,
                )

                usage = response.get("usage", {})
                input_tok = usage.get("input_tokens", 0)
                output_tok = usage.get("completion_tokens", 0)
                total_input_tokens += input_tok
                total_output_tokens += output_tok
                self.total_tokens_used = total_input_tokens + total_output_tokens

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
                # Keep system prompt + most recent messages to stay within MAX_MESSAGES_CHARS
                if len(messages) > 2:  # At least system + 1 message
                    total_chars = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
                    if total_chars > MAX_MESSAGES_CHARS:
                        # Strategy: keep system prompt + last N messages that fit
                        system_msg = messages[0]
                        recent_msgs = messages[1:]  # everything after system
                        # Keep removing oldest until we fit, but always remove paired messages together
                        # to avoid orphaned tool results (tool msg without preceding assistant tool_calls)
                        while recent_msgs and total_chars > MAX_MESSAGES_CHARS:
                            removed = recent_msgs.pop(0)
                            # If we just removed an assistant msg with tool_calls,
                            # also remove the following tool result msg to keep pairing intact
                            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                                if recent_msgs and recent_msgs[0].get("role") == "tool":
                                    recent_msgs.pop(0)
                            # Recalculate after removal
                            total_chars = len(json.dumps(system_msg, ensure_ascii=False)) + \
                                sum(len(json.dumps(m, ensure_ascii=False)) for m in recent_msgs)

                        # Final safety: if first msg after system is an orphaned tool result, drop it
                        while recent_msgs and recent_msgs[0].get("role") == "tool":
                            recent_msgs.pop(0)
                            total_chars = len(json.dumps(system_msg, ensure_ascii=False)) + \
                                sum(len(json.dumps(m, ensure_ascii=False)) for m in recent_msgs)

                        messages = [system_msg] + recent_msgs

                action = self.decision_engine.decide(output_items)

                if action.type == ActionType.RESPOND:
                    if not action.will_continue:
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
                            pass  # Don't let memory errors break tool execution

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
            self._current_session.status = "error" if self.error else "completed"
            self.session_mgr.update_session(self._current_session)
            self.status = self.status or "finished"

            # Memory system: save session summary and end session
            if self.memory_mgr and self.config.auto_remember:
                try:
                    # Store session summary
                    session_summary = {
                        "task": task,
                        "status": self.status,
                        "iterations": self._iteration,
                        "duration_sec": int(time.time() - self.start_time) if self.start_time else 0,
                        "error": self.error,
                    }

                    # Determine importance based on outcome
                    importance = 0.5
                    if self.error:
                        importance = 0.7  # Errors are worth remembering
                    elif self._iteration > 10:
                        importance = 0.6  # Complex tasks

                    self.memory_mgr.remember(
                        f"Session completed: {json.dumps(session_summary)}",
                        importance=importance,
                        tags=["session", "outcome"],
                        title=f"Session: {task[:50]}"
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


# ─── Multi-Round Reasoning Engine ────────────────────────────────────────

CHAIN_OF_THOUGHT_PROMPT = """You are an expert problem solver. Think step by step before taking action.

For each task:
1. ANALYZE: Break down the problem into components
2. PLAN: Create a detailed step-by-step plan
3. REASON: Think about potential challenges and solutions
4. EXECUTE: Take action based on your reasoning

Always show your thinking process before calling tools.

Format your reasoning as:
<thinking>
[Your detailed analysis and planning here]
</thinking>

Then call the appropriate tools."""


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
            for item in output:
                if item.get("type") == "message":
                    content = item.get("content", [])
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            return c.get("text", "")

            return "No reasoning output"

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
