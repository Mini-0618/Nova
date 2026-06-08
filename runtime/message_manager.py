"""
Message Manager
Handles message building, token estimation, and context window management
for the Codex-Local auto-loop engine.

v2: Smart trimming with 80% threshold, recent-round preservation,
    and key tool result retention.
"""

import json
from typing import List, Dict, Tuple


# Maximum characters for message history (~20k tokens)
MAX_MESSAGES_CHARS = 80_000

# Trigger trimming when context reaches this fraction of the limit
TRIM_THRESHOLD = 0.80

# Number of recent conversation rounds (user+assistant pairs) to always preserve
RECENT_ROUNDS_TO_KEEP = 5

# Maximum chars for a single tool result before summarizing
MAX_TOOL_RESULT_CHARS = 2000

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


def _group_into_rounds(messages: List[Dict]) -> List[List[Dict]]:
    """Group messages into conversation rounds.

    Each round is a user message followed by assistant + tool messages.
    Returns list of rounds, where each round is a list of messages.
    """
    rounds = []
    current_round = []

    for msg in messages:
        role = msg.get("role", "user")
        if role == "user" and current_round:
            # Start of a new round
            rounds.append(current_round)
            current_round = [msg]
        else:
            current_round.append(msg)

    if current_round:
        rounds.append(current_round)

    return rounds


def _summarize_tool_result(msg: Dict) -> Dict:
    """Summarize a tool result message to save space."""
    content = msg.get("content", "")
    if len(content) <= MAX_TOOL_RESULT_CHARS:
        return msg
    # Keep first and last portion with a note
    keep = MAX_TOOL_RESULT_CHARS // 2
    summarized = content[:keep] + f"\n... [TRUNCATED from {len(content)} chars] ...\n" + content[-keep:]
    return {**msg, "content": summarized}


def _trim_old_rounds(system_msg: Dict, messages: List[Dict], max_chars: int) -> List[Dict]:
    """Smart trimming: preserve system + recent N rounds + summarize old tool results.

    Strategy:
    1. Always keep system prompt
    2. Always keep the most recent RECENT_ROUNDS_TO_KEEP rounds intact
    3. For older rounds: summarize tool results, then drop oldest if still too big
    """
    total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in messages)

    # Already within limit
    if total_chars <= max_chars:
        return messages

    rounds = _group_into_rounds(messages)

    if len(rounds) <= RECENT_ROUNDS_TO_KEEP:
        # Few rounds: just do simple oldest-first trimming
        return _simple_trim(messages, max_chars - _msg_char_len(system_msg))

    # Split into old and recent
    old_rounds = rounds[:-RECENT_ROUNDS_TO_KEEP]
    recent_rounds = rounds[-RECENT_ROUNDS_TO_KEEP:]

    # Step 1: Summarize tool results in old rounds
    trimmed_old = []
    for round_msgs in old_rounds:
        trimmed_round = []
        for msg in round_msgs:
            if msg.get("role") == "tool":
                trimmed_round.append(_summarize_tool_result(msg))
            else:
                trimmed_round.append(msg)
        trimmed_old.append(trimmed_round)

    # Rebuild message list
    all_messages = []
    for r in trimmed_old:
        all_messages.extend(r)
    for r in recent_rounds:
        all_messages.extend(r)

    total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in all_messages)

    # Step 2: If still over limit, drop oldest old rounds entirely
    while trimmed_old and total_chars > max_chars:
        # Remove the oldest round (and its tool results)
        removed_round = trimmed_old.pop(0)
        for msg in removed_round:
            all_messages.remove(msg)  # Remove first occurrence
        total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in all_messages)

    # Step 3: If still over limit (shouldn't happen often), trim recent tool results too
    if total_chars > max_chars:
        all_messages = _simple_trim(all_messages, max_chars - _msg_char_len(system_msg))

    # Drop orphaned tool results at the front
    while all_messages and all_messages[0].get("role") == "tool":
        all_messages.pop(0)

    return all_messages


def _simple_trim(messages: List[Dict], max_chars: int) -> List[Dict]:
    """Simple oldest-first trimming, preserving tool-call pairing."""
    recent = list(messages)
    total_chars = sum(_msg_char_len(m) for m in recent)
    while recent and total_chars > max_chars:
        removed = recent.pop(0)
        if removed.get("role") == "assistant" and removed.get("tool_calls"):
            while recent and recent[0].get("role") == "tool":
                recent.pop(0)
        total_chars = sum(_msg_char_len(m) for m in recent)
    return recent


def _build_messages(task: str, history: List[Dict], system_prompt: str,
                    max_context_tokens: int = 0) -> List[Dict]:
    """Build message list with smart token-aware context window management.

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
            full_messages.append({"role": "user", "content": _TOOL_USE_REMINDER})

    full_messages.append({"role": "user", "content": task})

    system_msg = {"role": "system", "content": system_prompt}

    if max_context_tokens > 0:
        max_chars = max_context_tokens * 4
        total_chars = _msg_char_len(system_msg) + sum(_msg_char_len(m) for m in full_messages)

        # Trigger smart trimming at 80% threshold
        threshold_chars = int(max_chars * TRIM_THRESHOLD)
        if total_chars <= max_chars:
            return [system_msg] + full_messages

        # Smart trim
        trimmed = _trim_old_rounds(system_msg, full_messages, max_chars)
        return [system_msg] + trimmed
    else:
        # Legacy char-based limit
        total_chars = sum(_msg_char_len(m) for m in full_messages)
        if total_chars <= MAX_MESSAGES_CHARS:
            return [system_msg] + full_messages

        trimmed = _simple_trim(full_messages, MAX_MESSAGES_CHARS)
        while trimmed and trimmed[0].get("role") == "tool":
            trimmed.pop(0)
        return [system_msg] + trimmed
