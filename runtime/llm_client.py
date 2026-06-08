"""
LLM Client
Handles all LLM API communication: calling, streaming, response parsing,
model resolution, and verification.
"""

import os
import json
import logging
import time
import asyncio
import random
from typing import Optional, Dict, Any, List, Callable

from runtime.message_manager import _estimate_tokens

_log = logging.getLogger(__name__)

# ─── Model Registry ────────────────────────────────────────────────────────

# Well-known models and their default providers
_MODEL_PROVIDER_MAP: Dict[str, str] = {
    "deepseek-chat": "deepseek",
    "deepseek-coder": "deepseek",
    "deepseek-reasoner": "deepseek",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-4": "openai",
    "gpt-3.5-turbo": "openai",
    "MiMo": "xiaomi",
    "qwen-7b": "xiaomi",
    "codellama": "ollama",
    "llama3": "ollama",
}


# ─── Tool Format Conversion ───────────────────────────────────────────────

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


# ─── API Resolution ────────────────────────────────────────────────────────

def _resolve_api_url(provider: str = "") -> str:
    """Resolve API base URL from provider name or env override."""
    providers = {
        "deepseek": "https://api.deepseek.com/chat/completions",
        "openai": "https://api.openai.com/v1/chat/completions",
        "xiaomi": "https://api.xiaomi.com/v1/chat/completions",
        "ollama": "http://localhost:11434/v1/chat/completions",
    }

    # If provider is specified, use it directly (don't check env)
    if provider and provider in providers:
        return providers[provider]

    # Check env override for unspecified provider
    for var in ["CODEX_API_URL", "OPENAI_BASE_URL"]:
        url = os.environ.get(var)
        if url:
            return url.rstrip("/") + "/chat/completions"

    # Default
    return providers["deepseek"]


def _resolve_api_key() -> str:
    """Resolve API key from env, checking multiple sources."""
    for var in ["CODEX_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "XIAOMIMIMO_API_KEY"]:
        key = os.environ.get(var)
        if key:
            return key
    return ""


def _resolve_api_key_for_provider(provider: str) -> str:
    """Resolve API key for a specific provider."""
    provider_key_map = {
        "deepseek": ["DEEPSEEK_API_KEY", "CODEX_API_KEY"],
        "openai": ["OPENAI_API_KEY", "CODEX_API_KEY"],
        "xiaomi": ["XIAOMIMIMO_API_KEY", "CODEX_API_KEY"],
        "ollama": ["CODEX_API_KEY"],  # Ollama doesn't need a real key
    }
    key_vars = provider_key_map.get(provider, ["CODEX_API_KEY"])
    for var in key_vars:
        key = os.environ.get(var)
        if key:
            return key
    return ""


# ─── Provider Inference ────────────────────────────────────────────────────

def _infer_provider(model_name: str) -> str:
    """Infer provider from model name. Falls back to env-based detection."""
    # Check well-known map first
    for prefix, prov in _MODEL_PROVIDER_MAP.items():
        if model_name.startswith(prefix) or prefix in model_name:
            return prov
    # Fallback: if OPENAI_BASE_URL is set, assume openai-compatible
    if os.environ.get("OPENAI_BASE_URL"):
        return "openai"
    return "deepseek"


# ─── Model Listing ─────────────────────────────────────────────────────────

def list_available_models() -> List[Dict[str, Any]]:
    """List all configured/available models.

    Scans environment variables and well-known model registry.
    Returns list of {name, provider, url, available}.
    """
    models = []
    seen = set()

    # 1. Current model from env
    current_model = os.environ.get("CODEX_MODEL", "deepseek-chat")
    current_provider = os.environ.get("CODEX_PROVIDER", "")

    # 2. Scan well-known models -- include those whose provider has an API key
    for model_name, provider in _MODEL_PROVIDER_MAP.items():
        if model_name in seen:
            continue
        seen.add(model_name)
        url = _resolve_api_url(provider)
        key = _resolve_api_key_for_provider(provider)
        models.append({
            "name": model_name,
            "provider": provider,
            "url": url,
            "available": bool(key),
        })

    # 3. Add current model if not already listed
    if current_model not in seen:
        prov = current_provider or _infer_provider(current_model)
        models.append({
            "name": current_model,
            "provider": prov,
            "url": _resolve_api_url(prov),
            "available": True,
        })

    # 4. Add any extra models from CODEX_FALLBACK_MODELS env
    extra = os.environ.get("CODEX_FALLBACK_MODELS", "")
    if extra:
        for m in extra.split(","):
            m = m.strip()
            if m and m not in seen:
                seen.add(m)
                prov = _infer_provider(m)
                models.append({
                    "name": m,
                    "provider": prov,
                    "url": _resolve_api_url(prov),
                    "available": bool(_resolve_api_key_for_provider(prov)),
                })

    return models


# ─── Response Parsing ──────────────────────────────────────────────────────

def _convert_chat_to_response_format(chat_resp: Dict, model: str) -> Dict:
    """Convert Chat Completions response to internal response format."""
    import uuid
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


def _parse_sse_stream(resp, model: str, callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Parse an SSE streaming response and accumulate into standard response format.

    Args:
        resp: requests Response with stream=True
        model: Model name for the response
        callback: Optional callback called with each text chunk

    Returns:
        Response dict in the same format as _convert_chat_to_response_format
    """
    import uuid as _uuid

    accumulated_text = ""
    tool_calls_map: Dict[int, Dict] = {}  # index -> {id, name, arguments}
    finish_reason = None
    prompt_tokens = 0
    completion_tokens = 0

    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        # Extract usage if present (some providers include it in the last chunk)
        chunk_usage = chunk.get("usage")
        if chunk_usage:
            prompt_tokens = chunk_usage.get("prompt_tokens", prompt_tokens)
            completion_tokens = chunk_usage.get("completion_tokens", completion_tokens)

        choices = chunk.get("choices", [])
        if not choices:
            continue

        delta = choices[0].get("delta", {})
        finish_reason = choices[0].get("finish_reason") or finish_reason

        # Accumulate text content
        content_delta = delta.get("content", "")
        if content_delta:
            accumulated_text += content_delta
            if callback:
                try:
                    callback(content_delta)
                except Exception:
                    _log.warning("Streaming callback failed", exc_info=True)

        # Accumulate tool calls
        tc_delta = delta.get("tool_calls", [])
        for tc in tc_delta:
            idx = tc.get("index", 0)
            if idx not in tool_calls_map:
                tool_calls_map[idx] = {
                    "id": tc.get("id", ""),
                    "name": "",
                    "arguments": "",
                }
            if tc.get("id"):
                tool_calls_map[idx]["id"] = tc["id"]
            fn = tc.get("function", {})
            if fn.get("name"):
                tool_calls_map[idx]["name"] = fn["name"]
            if fn.get("arguments"):
                tool_calls_map[idx]["arguments"] += fn["arguments"]

    # Build output in standard format
    output = []
    if accumulated_text:
        output.append({
            "id": "msg_" + _uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": accumulated_text, "annotations": []}],
        })
    for idx in sorted(tool_calls_map.keys()):
        tc = tool_calls_map[idx]
        output.append({
            "id": "fc_" + _uuid.uuid4().hex,
            "type": "function_call",
            "status": "completed",
            "call_id": tc["id"] or f"call_{_uuid.uuid4().hex[:8]}",
            "name": tc["name"],
            "arguments": tc["arguments"] or "{}",
        })

    # Estimate token usage if not provided by the API
    if completion_tokens == 0 and accumulated_text:
        completion_tokens = _estimate_tokens(accumulated_text)

    return {
        "id": "resp_" + _uuid.uuid4().hex,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def _try_choices_format(response: Dict) -> Optional[List[Dict]]:
    """Try to extract output items from Chat Completions 'choices' format."""
    choices = response.get("choices")
    if not choices or not isinstance(choices, list) or len(choices) == 0:
        return None
    msg = choices[0].get("message", {})
    items = []
    content = msg.get("content", "")
    if content:
        items.append({
            "id": "msg_fallback", "type": "message", "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": content, "annotations": []}],
        })
    for tc in msg.get("tool_calls", []):
        fn = tc.get("function", {})
        items.append({
            "id": "fc_fallback_" + str(id(tc)), "type": "function_call",
            "status": "completed", "call_id": tc.get("id", ""),
            "name": fn.get("name", ""), "arguments": fn.get("arguments", "{}"),
        })
    return items


def _validate_output_item(item: Dict) -> Optional[Dict]:
    """Validate and normalize a single output item. Returns item or None."""
    if not isinstance(item, dict):
        return None
    item_type = item.get("type")
    if item_type == "function_call":
        if item.get("name"):
            return item
        tool_name = item.get("tool_name", item.get("function", {}).get("name", ""))
        if tool_name:
            item["name"] = tool_name
            return item
        return None
    if item_type == "message":
        content = item.get("content", [])
        if content and isinstance(content, list):
            return item
        if item.get("text"):
            return {
                "id": item.get("id", "msg_recovered"), "type": "message",
                "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": item["text"], "annotations": []}],
            }
        return None
    if item.get("name") and not item.get("type"):
        item["type"] = "function_call"
        return item
    if item.get("text") or item.get("content"):
        item["type"] = "message"
        return item
    return None


def _extract_output_items(response: Dict) -> List[Dict]:
    """Extract output items with validation and graceful fallback for malformed responses."""
    if not isinstance(response, dict):
        return []
    output = response.get("output")
    if output is None:
        result = _try_choices_format(response)
        return result if result is not None else []
    if not isinstance(output, list):
        return []
    return [v for v in (_validate_output_item(item) for item in output) if v is not None]


# ─── LLM Calling ───────────────────────────────────────────────────────────

async def _call_llm_async(messages: List[Dict], config,
                          api_key: str, provider: str, model: str,
                          stream_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Call the LLM directly via Chat Completions API with retry logic.

    Args:
        messages: Message list
        config: LoopConfig (needs: stream, temperature, max_output_tokens)
        api_key: API key string
        provider: Provider name
        model: Model name
        stream_callback: Optional callback for streaming chunks. Each chunk text is passed to it.
    """
    # Import TOOL_DEFINITIONS lazily to avoid circular imports
    from tools.executor import TOOL_DEFINITIONS

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
                tool_calls = [
                    {
                        "id": tc.get("id", f"call_{id(tc)}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                        },
                    }
                    for tc in msg["tool_calls"]
                ]
                chat_messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
            else:
                chat_messages.append({"role": "assistant", "content": content or ""})
        elif role == "tool":
            chat_messages.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", "unknown"),
                "content": content,
            })

    use_stream = config.stream and stream_callback is not None

    body = {
        "model": model,
        "messages": chat_messages,
        "stream": use_stream,
        "temperature": config.temperature,
        "max_tokens": config.max_output_tokens,
    }
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
                timeout=(10, 300 if use_stream else 120),  # longer timeout for streaming
                stream=use_stream,
            )
            # Check HTTP status before attempting to parse
            if resp.status_code != 200:
                err_body = resp.text or "no body"
                status = resp.status_code
                retryable = status in (429, 500, 502, 503, 504)
                if status == 400 and "context length" in err_body.lower():
                    raise RuntimeError(f"LLM API error {status}: {err_body}")
                if retryable and attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    delay *= 0.75 + 0.5 * random.random()
                    last_exception = RuntimeError(f"LLM API error {status} (attempt {attempt}/{max_retries}): {err_body[:500]}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise RuntimeError(f"LLM API error {status}: {err_body[:1000]}")

            if use_stream:
                return _parse_sse_stream(resp, model, stream_callback)
            else:
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
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                delay *= 0.75 + 0.5 * random.random()
                last_exception = RuntimeError(f"LLM API connection error (attempt {attempt}/{max_retries}): {e}")
                await asyncio.sleep(delay)
                continue
            else:
                raise RuntimeError(f"LLM API connection failed after {max_retries} retries: {e}") from e

    raise last_exception or RuntimeError("LLM API call failed after all retries")


# ─── Model Verification ────────────────────────────────────────────────────

async def _verify_model(model_name: str, provider: str = "") -> bool:
    """Send a minimal request to verify a model is reachable and responds."""
    try:
        # Import LoopConfig lazily to avoid circular imports
        from runtime.loop import LoopConfig

        messages = [{"role": "user", "content": "hi"}]
        config = LoopConfig(
            model=model_name,
            provider=provider or _infer_provider(model_name),
            max_output_tokens=8,
            temperature=0.0,
        )
        key = _resolve_api_key_for_provider(config.provider)
        if not key:
            key = _resolve_api_key()
        if not key:
            return False
        resp = await _call_llm_async(messages, config, key, config.provider, config.model)
        return bool(resp.get("output"))
    except Exception:
        return False
