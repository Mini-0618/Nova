"""
Codex-Local: OpenAI Responses API compatible bridge
Supports: DeepSeek, XiaoMi-MIMO, Ollama, Anthropic, OpenAI-compatible endpoints
"""

import os
import json
import time
import uuid
import asyncio
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
import threading


# ─── Provider Configurations ───────────────────────────────────────────────

PROVIDERS = {
    "deepseek": {
        "url": "https://api.deepseek.com/chat/completions",
        "model_map": {
            "deepseek-chat": "deepseek-chat",
            "deepseek-coder": "deepseek-coder",
        },
        "requires_prefix": False,
    },
    "xiaomi": {
        "url": "https://api.minimax.chat/v1/chat/completions",
        "model_map": {
            "mimo-v2.5": "MiniMax-Text-01",
        },
        "requires_prefix": False,
    },
    "ollama": {
        "url": "http://localhost:11434/api/chat",
        "model_map": {
            "llama3": "llama3",
            "qwen2.5": "qwen2.5",
            "codellama": "codellama",
        },
        "requires_prefix": False,
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "model_map": {
            "claude-opus-4-8": "claude-opus-4-8",
            "claude-sonnet-4-6": "claude-sonnet-4-6",
            "claude-haiku-4-5": "claude-haiku-4-5",
        },
        "requires_prefix": False,
    },
}


def get_provider() -> str:
    return os.environ.get("CODEX_PROVIDER", "deepseek")


def get_api_key() -> str:
    return os.environ.get("CODEX_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))


def get_model() -> str:
    return os.environ.get("CODEX_MODEL", "deepseek-chat")


# ─── Message Conversion ─────────────────────────────────────────────────────

def extract_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for item in content:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    out.append(str(item.get("text", "")))
                elif "output" in item:
                    out.append(str(item.get("output", "")))
                elif "type" in item and item["type"] == "text":
                    out.append(str(item.get("text", "")))
        return "\n".join([x for x in out if x])
    return str(content)


def convert_role(role: str) -> str:
    if role in ("system", "developer"):
        return "system"
    if role in ("assistant", "user", "tool"):
        return role
    return "user"


def responses_input_to_messages(body: dict) -> List[dict]:
    """
    Convert OpenAI Responses API format to Chat Completions format.
    Handles instructions, user input, function calls.
    """
    messages = []

    instructions = body.get("instructions")
    if instructions:
        messages.append({"role": "system", "content": str(instructions)})

    user_input = body.get("input", "")

    if isinstance(user_input, str):
        messages.append({"role": "user", "content": user_input})
        return messages

    if isinstance(user_input, list):
        for item in user_input:
            if not isinstance(item, dict):
                messages.append({"role": "user", "content": str(item)})
                continue

            item_type = item.get("type")

            if item_type == "function_call":
                call_id = item.get("call_id") or item.get("id") or ("call_" + uuid.uuid4().hex)
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": item.get("name", "unknown_tool"),
                            "arguments": item.get("arguments", "{}"),
                        },
                    }],
                })
                continue

            if item_type == "function_call_output":
                call_id = item.get("call_id") or item.get("id") or "unknown_call"
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": str(item.get("output", "")),
                })
                continue

            role = convert_role(item.get("role", "user"))
            text = extract_text(item.get("content", ""))

            if text:
                messages.append({"role": role, "content": text})

    if not messages:
        messages.append({"role": "user", "content": ""})

    return messages


def convert_tools(body: dict) -> List[dict]:
    """Convert OpenAI-style tools to Chat Completions format."""
    tools = body.get("tools") or []
    converted = []

    for tool in tools:
        if not isinstance(tool, dict):
            continue

        if tool.get("type") == "function":
            name = tool.get("name") or tool.get("function", {}).get("name")
            description = tool.get("description") or tool.get("function", {}).get("description", "")
            parameters = tool.get("parameters") or tool.get("function", {}).get("parameters") or {"type": "object", "properties": {}}

            if name:
                converted.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                })

    return converted


# ─── Provider Callers ──────────────────────────────────────────────────────

def call_deepseek(body: dict) -> dict:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")

    provider_cfg = PROVIDERS["deepseek"]
    model = body.get("model") or "deepseek-chat"

    payload = {
        "model": provider_cfg["model_map"].get(model, model),
        "messages": responses_input_to_messages(body),
        "stream": False,
    }

    tools = convert_tools(body)
    if tools:
        payload["tools"] = tools

    if body.get("temperature") is not None:
        payload["temperature"] = body.get("temperature")

    if body.get("max_output_tokens") is not None:
        payload["max_tokens"] = body.get("max_output_tokens")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        provider_cfg["url"],
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_xiaomi(body: dict) -> dict:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("CODEX_API_KEY (for XiaoMi) is not set")

    provider_cfg = PROVIDERS["xiaomi"]
    model = body.get("model") or "mimo-v2.5"

    payload = {
        "model": provider_cfg["model_map"].get(model, model),
        "messages": responses_input_to_messages(body),
        "stream": False,
    }

    tools = convert_tools(body)
    if tools:
        payload["tools"] = tools

    if body.get("temperature") is not None:
        payload["temperature"] = body.get("temperature")

    if body.get("max_output_tokens") is not None:
        payload["max_tokens"] = body.get("max_output_tokens")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        provider_cfg["url"],
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_ollama(body: dict) -> dict:
    provider_cfg = PROVIDERS["ollama"]
    model = body.get("model") or "llama3"

    messages = responses_input_to_messages(body)

    payload = {
        "model": provider_cfg["model_map"].get(model, model),
        "messages": messages,
        "stream": False,
    }

    tools = convert_tools(body)
    if tools:
        payload["tools"] = tools

    if body.get("temperature") is not None:
        payload["temperature"] = body.get("temperature")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        provider_cfg["url"],
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_anthropic(body: dict) -> dict:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    model = body.get("model") or "claude-sonnet-4-6"

    messages = responses_input_to_messages(body)

    system_msg = None
    for msg in messages:
        if msg["role"] == "system":
            system_msg = msg["content"]
            break

    auth_messages = [m for m in messages if m["role"] != "system"]

    payload = {
        "model": model,
        "messages": auth_messages,
        "max_tokens": body.get("max_output_tokens") or 4096,
    }

    if system_msg:
        payload["system"] = system_msg

    if body.get("temperature") is not None:
        payload["temperature"] = body.get("temperature")

    tools = convert_tools(body)
    if tools:
        payload["tools"] = tools

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


DISPATCH = {
    "deepseek": call_deepseek,
    "xiaomi": call_xiaomi,
    "ollama": call_ollama,
    "anthropic": call_anthropic,
}


def call_provider(body: dict) -> dict:
    provider = get_provider()
    if provider not in DISPATCH:
        raise ValueError(f"Unknown provider: {provider}")
    return DISPATCH[provider](body)


# ─── Response Formatting ────────────────────────────────────────────────────

def response_from_deepseek(body: dict, ds: dict) -> dict:
    now = int(time.time())
    response_id = "resp_" + uuid.uuid4().hex
    model = body.get("model") or "deepseek-chat"

    choice = (ds.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []

    output = []

    if text:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        })

    for tc in tool_calls:
        fn = tc.get("function") or {}
        output.append({
            "id": "fc_" + uuid.uuid4().hex,
            "type": "function_call",
            "status": "completed",
            "call_id": tc.get("id") or ("call_" + uuid.uuid4().hex),
            "name": fn.get("name", "unknown_tool"),
            "arguments": fn.get("arguments", "{}"),
        })

    if not output:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": "",
                "annotations": [],
            }],
        })

    usage = ds.get("usage") or {}
    return {
        "id": response_id,
        "object": "response",
        "created_at": now,
        "status": "completed",
        "error": None,
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def response_from_xiaomi(body: dict, ds: dict) -> dict:
    return response_from_deepseek(body, ds)


def response_from_ollama(body: dict, ds: dict) -> dict:
    now = int(time.time())
    response_id = "resp_" + uuid.uuid4().hex
    model = body.get("model") or "llama3"

    msg = ds.get("message") or {}
    text = msg.get("content") or ""
    tool_calls = msg.get("tool_calls") or []

    output = []

    if text:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        })

    for tc in tool_calls:
        fn = tc.get("function") or {}
        output.append({
            "id": "fc_" + uuid.uuid4().hex,
            "type": "function_call",
            "status": "completed",
            "call_id": tc.get("id") or ("call_" + uuid.uuid4().hex),
            "name": fn.get("name", "unknown_tool"),
            "arguments": fn.get("arguments", "{}"),
        })

    if not output:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": "",
                "annotations": [],
            }],
        })

    usage = ds.get("usage") or {}
    return {
        "id": response_id,
        "object": "response",
        "created_at": now,
        "status": "completed",
        "error": None,
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
    }


def response_from_anthropic(body: dict, ds: dict) -> dict:
    now = int(time.time())
    response_id = "resp_" + uuid.uuid4().hex
    model = body.get("model") or "claude-sonnet-4-6"

    output = []
    text = ds.get("content", [{}])[0].get("text", "") if isinstance(ds.get("content"), list) else ""

    if text:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        })

    # Anthropic tool use
    for tc in ds.get("content", []):
        if isinstance(tc, dict) and tc.get("type") == "tool_use":
            output.append({
                "id": "fc_" + uuid.uuid4().hex,
                "type": "function_call",
                "status": "completed",
                "call_id": tc.get("id") or ("call_" + uuid.uuid4().hex),
                "name": tc.get("name", "unknown_tool"),
                "arguments": tc.get("input", {}),
            })

    if not output:
        output.append({
            "id": "msg_" + uuid.uuid4().hex,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": "",
                "annotations": [],
            }],
        })

    usage = ds.get("usage") or {}
    return {
        "id": response_id,
        "object": "response",
        "created_at": now,
        "status": "completed",
        "error": None,
        "model": model,
        "output": output,
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


RESPONSE_FORMATTERS = {
    "deepseek": response_from_deepseek,
    "xiaomi": response_from_xiaomi,
    "ollama": response_from_ollama,
    "anthropic": response_from_anthropic,
}


# ─── HTTP Handler ───────────────────────────────────────────────────────────

class CodexBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass  # suppress default logging

    def send_json(self, status: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_sse_event(self, event: str, obj: dict):
        data = json.dumps(obj, ensure_ascii=False)
        self.wfile.write(("event: " + event + "\n").encode("utf-8"))
        self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
        self.wfile.flush()

    def send_sse_response(self, response: dict):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        started = dict(response)
        started["status"] = "in_progress"
        started["output"] = []
        self.send_sse_event("response.created", started)

        for index, item in enumerate(response.get("output", [])):
            self.send_sse_event("response.output_item.added", {
                "output_index": index,
                "item": item,
            })

            if item.get("type") == "message":
                content = item.get("content") or []
                text = ""
                if content:
                    text = content[0].get("text", "")

                if text:
                    chunk_size = 300
                    for pos in range(0, len(text), chunk_size):
                        self.send_sse_event("response.output_text.delta", {
                            "item_id": item.get("id"),
                            "output_index": index,
                            "content_index": 0,
                            "delta": text[pos:pos + chunk_size],
                        })

                    self.send_sse_event("response.output_text.done", {
                        "item_id": item.get("id"),
                        "output_index": index,
                        "content_index": 0,
                        "text": text,
                    })

            self.send_sse_event("response.output_item.done", {
                "output_index": index,
                "item": item,
            })

        self.send_sse_event("response.completed", response)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def do_GET(self):
        if self.path == "/v1/models":
            provider = get_provider()
            models = {
                "deepseek": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
                "xiaomi": ["mimo-v2.5"],
                "ollama": ["llama3", "qwen2.5", "codellama"],
                "anthropic": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5"],
            }
            self.send_json(200, {
                "object": "list",
                "data": [{"id": m, "object": "model"} for m in models.get(provider, ["unknown"])],
            })
            return

        if self.path == "/health":
            self.send_json(200, {"status": "ok", "provider": get_provider(), "model": get_model()})
            return

        self.send_json(404, {"error": "not found", "path": self.path})

    def do_POST(self):
        if self.path != "/v1/responses":
            self.send_json(404, {"error": "not found", "path": self.path})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw) if raw else {}

            provider = get_provider()
            ds = call_provider(body)
            formatter = RESPONSE_FORMATTERS.get(provider, response_from_deepseek)
            response = formatter(body, ds)

            if body.get("stream"):
                self.send_sse_response(response)
            else:
                self.send_json(200, response)

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            self.send_json(e.code, {
                "error": "provider_http_error",
                "status": e.code,
                "body": err,
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.send_json(500, {
                "error": "bridge_error",
                "message": str(e),
            })


# ─── Server ─────────────────────────────────────────────────────────────────

def run_server(host: str = "127.0.0.1", port: int = 8787):
    server = ThreadingHTTPServer((host, port), CodexBridgeHandler)
    print(f"[codex-local] Bridge running at http://{host}:{port}/v1/responses")
    print(f"[codex-local] Provider: {get_provider()} | Model: {get_model()}")
    print(f"[codex-local] Health:  http://{host}:{port}/health")
    server.serve_forever()


if __name__ == "__main__":
    run_server()