"""
Codex-Local Agent Brain
纯LLM推理接口，不涉及工具执行。
支持 DeepSeek / 小米 / Ollama / Anthropic 模型。
"""

import os
import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List


class AgentBrain:
    """
    Agent的大脑，纯做推理。
    对接 codex-local 的 bridge API 或直接调用各 Provider。
    """

    def __init__(
        self,
        model: str = None,
        provider: str = None,
        api_key: str = None,
        base_url: str = None,
        temperature: float = 0.5,
        max_tokens: int = 2048,
    ):
        self.model = model or os.environ.get("CODEX_MODEL", "deepseek-chat")
        self.provider = provider or os.environ.get("CODEX_PROVIDER", "deepseek")
        self.api_key = api_key or os.environ.get("CODEX_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.environ.get("CODEX_BRIDGE_URL", "")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _get_provider_config(self) -> Dict[str, Any]:
        """获取 Provider 配置"""
        configs = {
            "deepseek": {
                "url": "https://api.deepseek.com/chat/completions",
                "key_env": "DEEPSEEK_API_KEY",
                "model_map": {"deepseek-chat": "deepseek-chat", "deepseek-coder": "deepseek-coder"},
                "headers": lambda key: {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            },
            "xiaomi": {
                "url": "https://api.minimax.chat/v1/chat/completions",
                "key_env": "CODEX_API_KEY",
                "model_map": {"mimo-v2.5": "MiniMax-Text-01"},
                "headers": lambda key: {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            },
            "anthropic": {
                "url": "https://api.anthropic.com/v1/messages",
                "key_env": "ANTHROPIC_API_KEY",
                "model_map": {
                    "claude-sonnet-4-6": "claude-sonnet-4-6",
                    "claude-opus-4-8": "claude-opus-4-8",
                    "claude-haiku-4-5": "claude-haiku-4-5",
                },
                "headers": lambda key: {
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            },
            "ollama": {
                "url": "http://localhost:11434/api/chat",
                "key_env": None,
                "model_map": {"llama3": "llama3", "qwen2.5": "qwen2.5"},
                "headers": lambda _: {"Content-Type": "application/json"},
            },
        }
        return configs.get(self.provider, configs["deepseek"])

    def _make_messages(self, prompt: str, system: str = "") -> List[Dict]:
        """构建消息格式"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def think(self, prompt: str, system: str = "", json_output: bool = False) -> str:
        """
        核心思考函数。
        发送 prompt 给 LLM，返回模型的文本回复。

        Args:
            prompt: 用户提示
            system: 系统提示（可选）
            json_output: 是否要求返回 JSON 格式（会改 system prompt）

        Returns:
            LLM 生成的文本
        """
        cfg = self._get_provider_config()

        # 优先用 bridge URL（统一入口）
        if self.base_url:
            url = self.base_url.rstrip("/") + "/v1/responses"
            payload = {
                "model": self.model,
                "input": self._make_messages(prompt, system),
                "stream": False,
                "max_output_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    # 从 Responses API 格式中提取文本
                    for item in result.get("output", []):
                        if item.get("type") == "message":
                            for c in item.get("content", []):
                                if c.get("type") == "output_text":
                                    return c.get("text", "").strip()
                    return str(result)
            except Exception as e:
                return f"[Brain Error] {e}"

        # 直接调用 Provider API
        key = self.api_key
        if not key and cfg["key_env"]:
            key = os.environ.get(cfg["key_env"], "")

        messages = self._make_messages(prompt, system)
        model_mapped = cfg["model_map"].get(self.model, self.model)

        if self.provider == "anthropic":
            system_msg = system
            auth_messages = [m for m in messages if m["role"] != "system"]
            payload = {
                "model": model_mapped,
                "messages": auth_messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
            if system_msg:
                payload["system"] = system_msg
        else:
            payload = {
                "model": model_mapped,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = cfg["headers"](key)
        if self.provider == "ollama":
            # Ollama 用简化格式
            payload_ollama = {
                "model": model_mapped,
                "messages": messages,
                "stream": False,
            }
            data = json.dumps(payload_ollama, ensure_ascii=False).encode("utf-8")

        try:
            with urllib.request.urlopen(
                urllib.request.Request(cfg["url"], data=data, headers=headers, method="POST"),
                timeout=120,
            ) as resp:
                result = json.loads(resp.read().decode("utf-8"))

                if self.provider == "anthropic":
                    for c in result.get("content", []):
                        if c.get("type") == "text":
                            return c["text"].strip()
                    return str(result)
                else:
                    # Chat completions 格式
                    choices = result.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        return msg.get("content", "").strip()
                    return str(result)

        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            return f"[HTTP {e.code}] {err[:200]}"
        except Exception as e:
            return f"[Brain Error] {e}"

    def think_json(self, prompt: str, system: str = "") -> Dict[str, Any]:
        """
        要求 LLM 返回 JSON，自动解析。
        失败时返回 {"error": "..."}
        """
        full_system = (system or "") + "\n\n你必须只返回一个有效的JSON对象，不要有任何其他文字。"
        text = self.think(prompt, system=full_system)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": f"LLM返回的不是有效JSON: {text[:200]}"}

    def think_structured(
        self,
        prompt: str,
        system: str = "",
        schema: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        结构化输出：要求 LLM 按 schema 返回。
        schema 格式参考 JSON Schema（简化版）。
        目前通过 text + think_json 实现，未来可接入 tool_use。
        """
        # 简单实现：把 schema 要求加到 prompt 里
        if schema:
            schema_desc = json.dumps(schema, ensure_ascii=False, indent=2)
            hint = f"\n\n请严格按照以下JSON Schema返回：\n{schema_desc}"
            prompt = prompt + hint
        return self.think_json(prompt, system=system)


# ─── 测试 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    brain = AgentBrain(model="deepseek-chat", provider="deepseek")

    print("=== Brain 测试 ===")
    print("提问：你是一个任务规划助手吗？")
    reply = brain.think("你好，简单介绍一下你自己。")
    print(f"回复：{reply}")

    print("\n提问：1+1等于几？")
    reply = brain.think("1+1等于几？直接回答数字。")
    print(f"回复：{reply}")