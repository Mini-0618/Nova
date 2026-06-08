"""
Message Manager
Handles message building, token estimation, and context window management
for the Codex-Local auto-loop engine.
"""

import json
from typing import List, Dict


# Maximum characters for message history (~20k tokens)
MAX_MESSAGES_CHARS = 80_000

# Reminder injected when the model describes tools in text instead of calling them
_TOOL_USE_REMINDER = (
    "You must use tools. Call Write to create files, Bash to execute commands. "
    "Do not describe what you would do."
)


def _estimate_tokens(text: str) -> int:
    """Estimate token count: ~1 token per 4 characters."""
    return len(text) // 4 + 1


def _msg_char_len(msg: Dict) -> int:
    """Get the serialized char length of a message."""
    return len(json.dumps(msg, ensure_ascii=False))


def _build_messages(task: str, history: List[Dict], system_prompt: str,
                    max_context_tokens: int = 0) -> List[Dict]:
    """Build message list with token-aware context window management.

    Args:
        task: Current user task
        history: Previous message history
        system_prompt: System prompt
        max_context_tokens: Max context tokens (0 = use legacy char-based limit)
    """
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

    # Auto-inject tool-use reminder if last assistant message had no tool_calls
    if full_messages:
        last_assistant = None
        for m in reversed(full_messages):
            if m.get("role") == "assistant":
                last_assistant = m
                break
        if last_assistant and not last_assistant.get("tool_calls"):
            # Last assistant output was pure text (no tools) -- remind it to use tools
            full_messages.append({"role": "user", "content": _TOOL_USE_REMINDER})

    full_messages.append({"role": "user", "content": task})

    system_msg = {"role": "system", "content": system_prompt}

    if max_context_tokens > 0:
        # Token-based context management: 1 token approx 4 chars
        max_chars = max_context_tokens * 4
        total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in full_messages)

        if total_chars <= max_chars:
            return [system_msg] + full_messages

        # Truncate oldest messages while preserving tool-call pairing
        recent = list(full_messages)
        while recent and total_chars > max_chars:
            removed = recent.pop(0)
            # If removed assistant msg with tool_calls, also remove following tool results
            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                while recent and recent[0].get("role") == "tool":
                    recent.pop(0)
            total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in recent)

        # Drop orphaned tool results at the front
        while recent and recent[0].get("role") == "tool":
            recent.pop(0)

        return [system_msg] + recent
    else:
        # Legacy char-based limit
        total_chars = sum(_msg_char_len(m) for m in full_messages)

        if total_chars <= MAX_MESSAGES_CHARS:
            return [system_msg] + full_messages

        recent = list(full_messages)
        while recent and total_chars > MAX_MESSAGES_CHARS:
            removed = recent.pop(0)
            if removed.get("role") == "assistant" and removed.get("tool_calls"):
                while recent and recent[0].get("role") == "tool":
                    recent.pop(0)
            total_chars = sum(_msg_char_len(m) for m in recent)

        while recent and recent[0].get("role") == "tool":
            recent.pop(0)

        return [system_msg] + recent
