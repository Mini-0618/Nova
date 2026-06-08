"""Tests for runtime.llm_client module."""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.llm_client import (
    _convert_tools_to_openai_format,
    _resolve_api_url,
    _resolve_api_key,
    _resolve_api_key_for_provider,
    _infer_provider,
    list_available_models,
    _convert_chat_to_response_format,
    _parse_sse_stream,
    _extract_output_items,
    _MODEL_PROVIDER_MAP,
)


class TestConvertToolsToOpenaiFormat:
    def test_already_nested(self):
        tools = [{"type": "function", "function": {"name": "Foo", "parameters": {}}}]
        result = _convert_tools_to_openai_format(tools)
        assert result == tools

    def test_flat_format(self):
        tools = [{"type": "function", "name": "Foo", "description": "test", "parameters": {"type": "object"}}]
        result = _convert_tools_to_openai_format(tools)
        assert result[0]["function"]["name"] == "Foo"
        assert result[0]["function"]["description"] == "test"

    def test_non_dict_skipped(self):
        tools = [42, "not a dict", {"type": "function", "name": "Bar"}]
        result = _convert_tools_to_openai_format(tools)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "Bar"

    def test_unknown_type_passed_through(self):
        tools = [{"type": "unknown", "name": "X"}]
        result = _convert_tools_to_openai_format(tools)
        assert result[0]["type"] == "unknown"

    def test_empty_list(self):
        assert _convert_tools_to_openai_format([]) == []


class TestResolveApiUrl:
    def test_returns_string_ending_with_completions(self):
        url = _resolve_api_url("deepseek")
        assert isinstance(url, str)
        assert url.endswith("/chat/completions")

    def test_openai_returns_url(self):
        url = _resolve_api_url("openai")
        assert isinstance(url, str)
        assert url.endswith("/chat/completions")

    def test_ollama_returns_url(self):
        url = _resolve_api_url("ollama")
        assert isinstance(url, str)
        assert url.endswith("/chat/completions")

    def test_env_override(self):
        old = os.environ.get("CODEX_API_URL")
        try:
            os.environ["CODEX_API_URL"] = "https://custom.api.com"
            url = _resolve_api_url("")  # empty provider triggers env check
            assert "custom.api.com" in url
        finally:
            if old:
                os.environ["CODEX_API_URL"] = old
            else:
                os.environ.pop("CODEX_API_URL", None)

    def test_unknown_provider_returns_url(self):
        url = _resolve_api_url("nonexistent-provider")
        assert isinstance(url, str)
        assert url.endswith("/chat/completions")


class TestResolveApiKey:
    def test_returns_string(self):
        key = _resolve_api_key()
        assert isinstance(key, str)

    def test_env_override(self):
        old = os.environ.get("CODEX_API_KEY")
        try:
            os.environ["CODEX_API_KEY"] = "test-key-123"
            assert _resolve_api_key() == "test-key-123"
        finally:
            if old:
                os.environ["CODEX_API_KEY"] = old
            else:
                os.environ.pop("CODEX_API_KEY", None)


class TestResolveApiKeyForProvider:
    def test_deepseek(self):
        key = _resolve_api_key_for_provider("deepseek")
        assert isinstance(key, str)

    def test_ollama_returns_string(self):
        key = _resolve_api_key_for_provider("ollama")
        assert isinstance(key, str)


class TestInferProvider:
    def test_deepseek_models(self):
        assert _infer_provider("deepseek-chat") == "deepseek"
        assert _infer_provider("deepseek-coder") == "deepseek"

    def test_openai_models(self):
        assert _infer_provider("gpt-4o") == "openai"
        assert _infer_provider("gpt-3.5-turbo") == "openai"

    def test_ollama_models(self):
        assert _infer_provider("codellama") == "ollama"

    def test_unknown_falls_back(self):
        prov = _infer_provider("some-unknown-model")
        assert prov in ("deepseek", "openai")


class TestListAvailableModels:
    def test_returns_list(self):
        models = list_available_models()
        assert isinstance(models, list)

    def test_each_has_required_keys(self):
        models = list_available_models()
        for m in models:
            assert "name" in m
            assert "provider" in m
            assert "url" in m
            assert "available" in m

    def test_contains_deepseek(self):
        models = list_available_models()
        names = [m["name"] for m in models]
        assert "deepseek-chat" in names

    def test_extra_env_models(self):
        old = os.environ.get("CODEX_FALLBACK_MODELS", "")
        try:
            os.environ["CODEX_FALLBACK_MODELS"] = "custom-model-x"
            models = list_available_models()
            names = [m["name"] for m in models]
            assert "custom-model-x" in names
        finally:
            if old:
                os.environ["CODEX_FALLBACK_MODELS"] = old
            else:
                os.environ.pop("CODEX_FALLBACK_MODELS", None)


class TestConvertChatToResponseFormat:
    def test_basic_response(self):
        chat = {
            "choices": [{"message": {"content": "hello world"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        result = _convert_chat_to_response_format(chat, "test-model")
        assert result["model"] == "test-model"
        assert result["status"] == "completed"
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "message"
        assert result["output"][0]["content"][0]["text"] == "hello world"
        assert result["usage"]["input_tokens"] == 10

    def test_with_tool_calls(self):
        chat = {
            "choices": [{"message": {
                "content": "",
                "tool_calls": [{"id": "tc1", "function": {"name": "Write", "arguments": "{}"}}],
            }}],
            "usage": {},
        }
        result = _convert_chat_to_response_format(chat, "m")
        assert len(result["output"]) == 1
        assert result["output"][0]["type"] == "function_call"
        assert result["output"][0]["name"] == "Write"

    def test_empty_choices(self):
        chat = {"choices": [], "usage": {}}
        result = _convert_chat_to_response_format(chat, "m")
        assert result["output"] == []


class TestExtractOutputItems:
    def test_normal_output(self):
        resp = {"output": [
            {"type": "message", "content": [{"type": "output_text", "text": "hi"}]},
        ]}
        items = _extract_output_items(resp)
        assert len(items) == 1

    def test_fallback_to_choices(self):
        resp = {"choices": [{"message": {"content": "hello"}}]}
        items = _extract_output_items(resp)
        assert len(items) == 1
        assert items[0]["type"] == "message"

    def test_none_response(self):
        assert _extract_output_items(None) == []

    def test_empty_output(self):
        assert _extract_output_items({"output": []}) == []

    def test_function_call_without_name_filtered(self):
        resp = {"output": [{"type": "function_call", "name": ""}]}
        items = _extract_output_items(resp)
        assert len(items) == 0

    def test_function_call_with_name_kept(self):
        resp = {"output": [{"type": "function_call", "name": "Write", "arguments": "{}"}]}
        items = _extract_output_items(resp)
        assert len(items) == 1

    def test_recover_text_field(self):
        resp = {"output": [{"type": "message", "text": "hello"}]}
        items = _extract_output_items(resp)
        assert len(items) == 1
        assert items[0]["content"][0]["text"] == "hello"

    def test_unknown_type_with_name_recovered(self):
        resp = {"output": [{"name": "Foo", "arguments": "{}"}]}
        items = _extract_output_items(resp)
        assert len(items) == 1
        assert items[0]["type"] == "function_call"


class TestModelProviderMap:
    def test_has_deepseek(self):
        assert "deepseek-chat" in _MODEL_PROVIDER_MAP

    def test_has_openai(self):
        assert "gpt-4o" in _MODEL_PROVIDER_MAP

    def test_has_ollama(self):
        assert "codellama" in _MODEL_PROVIDER_MAP


class TestParseSseStream:
    def test_basic_text_stream(self):
        """Simulate a simple SSE stream with text chunks."""
        lines = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" World"},"finish_reason":"stop"}]}',
            'data: [DONE]',
        ]

        class FakeResp:
            def iter_lines(self, decode_unicode=True):
                return iter(lines)

        result = _parse_sse_stream(FakeResp(), "test-model")
        assert result["model"] == "test-model"
        assert len(result["output"]) == 1
        assert result["output"][0]["content"][0]["text"] == "Hello World"

    def test_stream_with_callback(self):
        lines = [
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":"stop"}]}',
            'data: [DONE]',
        ]

        class FakeResp:
            def iter_lines(self, decode_unicode=True):
                return iter(lines)

        chunks = []
        result = _parse_sse_stream(FakeResp(), "m", callback=lambda c: chunks.append(c))
        assert chunks == ["Hi"]

    def test_stream_with_tool_calls(self):
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"tc1","function":{"name":"Write"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"p"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"ath\\":\\"x.py\\"}"}}]},"finish_reason":"stop"}]}',
            'data: [DONE]',
        ]

        class FakeResp:
            def iter_lines(self, decode_unicode=True):
                return iter(lines)

        result = _parse_sse_stream(FakeResp(), "m")
        tc_items = [o for o in result["output"] if o["type"] == "function_call"]
        assert len(tc_items) == 1
        assert tc_items[0]["name"] == "Write"
