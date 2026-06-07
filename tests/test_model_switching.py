"""
Tests for model hot-switching and fallback logic.
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

# Ensure project root on path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from runtime.loop import (
    CodexLoop,
    LoopConfig,
    list_available_models,
    _infer_provider,
    _resolve_api_url,
    _verify_model,
)


# ─── list_available_models ──────────────────────────────────────────────────


class TestListAvailableModels:
    def test_returns_list_of_dicts(self):
        models = list_available_models()
        assert isinstance(models, list)
        for m in models:
            assert "name" in m
            assert "provider" in m
            assert "url" in m
            assert "available" in m

    def test_contains_deepseek(self):
        models = list_available_models()
        names = [m["name"] for m in models]
        assert "deepseek-chat" in names

    def test_available_flag_reflects_env(self):
        """Models whose provider has an API key should be marked available."""
        # We know at least one key is set in the test env (CODEX_API_KEY or DEEPSEEK_API_KEY)
        models = list_available_models()
        available = [m for m in models if m["available"]]
        # At least one model should be available in any working dev env
        assert len(available) >= 1

    def test_includes_extra_env_models(self):
        old = os.environ.get("CODEX_FALLBACK_MODELS", "")
        try:
            os.environ["CODEX_FALLBACK_MODELS"] = "my-custom-model,another-model"
            models = list_available_models()
            names = [m["name"] for m in models]
            assert "my-custom-model" in names
            assert "another-model" in names
        finally:
            if old:
                os.environ["CODEX_FALLBACK_MODELS"] = old
            else:
                os.environ.pop("CODEX_FALLBACK_MODELS", None)


# ─── _infer_provider ────────────────────────────────────────────────────────


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
        assert prov in ("deepseek", "openai")  # depends on OPENAI_BASE_URL


# ─── switch_model ───────────────────────────────────────────────────────────


class TestSwitchModel:
    @pytest.fixture
    def loop(self):
        config = LoopConfig(model="deepseek-chat", provider="deepseek")
        return CodexLoop(config)

    @pytest.mark.asyncio
    async def test_switch_same_model_returns_success(self, loop):
        result = await loop.switch_model("deepseek-chat", "deepseek")
        assert result["success"] is True
        assert result["old_model"] == "deepseek-chat"
        assert result["new_model"] == "deepseek-chat"
        assert result.get("note") == "already using this model"

    @pytest.mark.asyncio
    async def test_switch_model_updates_config(self, loop):
        with patch("runtime.loop._verify_model", new_callable=AsyncMock, return_value=True):
            result = await loop.switch_model("gpt-4o", "openai")
        assert result["success"] is True
        assert loop.config.model == "gpt-4o"
        assert loop.config.provider == "openai"

    @pytest.mark.asyncio
    async def test_switch_model_records_history(self, loop):
        with patch("runtime.loop._verify_model", new_callable=AsyncMock, return_value=True):
            await loop.switch_model("gpt-4o")
        history = loop.get_model_switch_history()
        assert len(history) == 1
        assert history[0]["to"] == "gpt-4o"
        assert history[0]["reason"] == "manual"

    @pytest.mark.asyncio
    async def test_switch_model_verifies_first(self, loop):
        """If verification fails, switch should not happen."""
        with patch("runtime.loop._verify_model", new_callable=AsyncMock, return_value=False):
            result = await loop.switch_model("bad-model", "deepseek")
        assert result["success"] is False
        assert "verification" in result["error"].lower()
        assert loop.config.model == "deepseek-chat"  # unchanged

    @pytest.mark.asyncio
    async def test_switch_model_resets_failure_counter(self, loop):
        loop._consecutive_failures = 5
        with patch("runtime.loop._verify_model", new_callable=AsyncMock, return_value=True):
            await loop.switch_model("gpt-4o")
        assert loop._consecutive_failures == 0


# ─── Fallback logic ─────────────────────────────────────────────────────────


class TestFallback:
    def test_try_fallback_switches_to_next(self):
        config = LoopConfig(
            model="primary-model",
            provider="deepseek",
            fallback_models=["fallback-a", "fallback-b"],
        )
        loop = CodexLoop(config)
        result = loop._try_fallback()
        assert result == "fallback-a"
        assert loop.config.model == "fallback-a"
        assert loop._fallback_index == 1

    def test_try_fallback_second_model(self):
        config = LoopConfig(
            model="primary-model",
            provider="deepseek",
            fallback_models=["fallback-a", "fallback-b"],
        )
        loop = CodexLoop(config)
        loop._try_fallback()  # first
        result = loop._try_fallback()  # second
        assert result == "fallback-b"
        assert loop.config.model == "fallback-b"
        assert loop._fallback_index == 2

    def test_try_fallback_exhausted_returns_none(self):
        config = LoopConfig(
            model="primary-model",
            provider="deepseek",
            fallback_models=["fallback-a"],
        )
        loop = CodexLoop(config)
        loop._try_fallback()  # use up the only fallback
        result = loop._try_fallback()
        assert result is None

    def test_try_fallback_no_fallbacks_configured(self):
        config = LoopConfig(model="primary-model", provider="deepseek")
        loop = CodexLoop(config)
        result = loop._try_fallback()
        assert result is None

    def test_try_fallback_records_history(self):
        config = LoopConfig(
            model="primary-model",
            provider="deepseek",
            fallback_models=["fallback-a"],
        )
        loop = CodexLoop(config)
        loop._try_fallback()
        history = loop.get_model_switch_history()
        assert len(history) == 1
        assert history[0]["reason"] == "auto_fallback"
        assert history[0]["to"] == "fallback-a"

    def test_fallback_threshold_is_configurable(self):
        config = LoopConfig(
            model="primary-model",
            provider="deepseek",
            fallback_models=["fb"],
            fallback_threshold=5,
        )
        assert config.fallback_threshold == 5

    def test_fallback_increments_index(self):
        config = LoopConfig(
            model="p",
            provider="deepseek",
            fallback_models=["a", "b", "c"],
        )
        loop = CodexLoop(config)
        assert loop._fallback_index == 0
        loop._try_fallback()
        assert loop._fallback_index == 1
        loop._try_fallback()
        assert loop._fallback_index == 2


# ─── LLM call with fallback (integration-level with mocks) ──────────────────


class TestFallbackIntegration:
    @pytest.mark.asyncio
    async def test_consecutive_failures_trigger_fallback(self):
        """After N failures, loop should auto-switch to fallback model."""
        config = LoopConfig(
            model="bad-model",
            provider="deepseek",
            fallback_models=["good-model"],
            fallback_threshold=2,
            max_iterations=3,
        )
        loop = CodexLoop(config)
        call_count = 0
        models_called = []

        async def mock_call_llm(messages, cfg, key, provider, model, stream_callback=None):
            nonlocal call_count
            call_count += 1
            models_called.append(model)
            if model == "bad-model":
                raise RuntimeError("Simulated LLM failure")
            # good-model succeeds — return a minimal valid response
            return {
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": model,
                "output": [{
                    "id": "msg_test",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "done", "annotations": []}],
                }],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }

        with patch("runtime.loop._call_llm_async", side_effect=mock_call_llm):
            with patch("runtime.loop._resolve_api_key", return_value="fake-key"):
                result = await loop.run_task("test task")

        # After 2 failures on bad-model, it should have switched to good-model
        assert "good-model" in models_called
        assert loop.config.model == "good-model"
        assert loop._consecutive_failures == 0  # reset after success

    @pytest.mark.asyncio
    async def test_no_fallback_when_below_threshold(self):
        """If failures are below threshold, no fallback should occur."""
        config = LoopConfig(
            model="flaky-model",
            provider="deepseek",
            fallback_models=["backup-model"],
            fallback_threshold=5,
            max_iterations=3,
        )
        loop = CodexLoop(config)
        models_called = []

        call_count = 0
        async def mock_call_llm(messages, cfg, key, provider, model, stream_callback=None):
            nonlocal call_count
            call_count += 1
            models_called.append(model)
            if call_count <= 2:
                raise RuntimeError("Temporary failure")
            return {
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": model,
                "output": [{
                    "id": "msg_test",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "done", "annotations": []}],
                }],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }

        with patch("runtime.loop._call_llm_async", side_effect=mock_call_llm):
            with patch("runtime.loop._resolve_api_key", return_value="fake-key"):
                result = await loop.run_task("test task")

        # All calls should be to the same model (no fallback triggered)
        assert all(m == "flaky-model" for m in models_called)
        assert "backup-model" not in models_called


# ─── LoopConfig defaults ────────────────────────────────────────────────────


class TestLoopConfigDefaults:
    def test_fallback_models_default_empty(self):
        config = LoopConfig()
        assert config.fallback_models == []

    def test_fallback_threshold_default(self):
        config = LoopConfig()
        assert config.fallback_threshold == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
