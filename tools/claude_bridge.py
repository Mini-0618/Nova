"""
Codex-Local Claude Code Bridge
Bridges Claude Code's MCP protocol to act as a model provider.
This lets Codex-Local use Claude Code's tool ecosystem and model access.
"""

import os
import sys
import json
import asyncio
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
from concurrent.futures._base import TimeoutError as FuturesTimeoutError
import urllib.request
import urllib.error

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ─── Claude Code MCP Protocol ───────────────────────────────────────────────

CLAUDE_CODE_PATHS = [
    "C:/Users/联想/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude-code.cmd",
    "C:/Users/联想/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude-code",
    "/c/Users/铸/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude-code.cmd",
]

CLAUDE_CODE_BIN = None
for p in CLAUDE_CODE_PATHS:
    pp = Path(p)
    if pp.exists():
        CLAUDE_CODE_BIN = str(pp)
        break


@dataclass
class ClaudeMessage:
    role: str
    content: str
    tool_calls: Optional[List[Dict]] = None


@dataclass
class ClaudeResponse:
    content: str
    tool_calls: List[Dict] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


class ClaudeCodeBridge:
    """
    Bridge to Claude Code - uses Claude Code as a tool-rich model provider.

    Claude Code has full MCP tool access and a capable model.
    This bridge lets Codex-Local send tasks to Claude Code and get results.

    Two modes:
    1. STDIO mode: Spawn Claude Code as subprocess, talk JSON-RPC over stdin/stdout
    2. HTTP mode: Use Claude Code's MCP HTTP server (if available)

    Usage:
        bridge = ClaudeCodeBridge()
        response = bridge.chat([{"role": "user", "content": "Do X"}], tools=[...])
    """

    def __init__(self, workspace_root: str = "D:/"):
        self.workspace_root = workspace_root
        self.claude_bin = CLAUDE_CODE_BIN
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._reader_thread: Optional[threading.Thread] = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._reader_running = False
        self._output_buffer = ""

        # Try to find Claude Code
        if not self.claude_bin:
            # Try via npx
            result = subprocess.run(
                ["npx", "--yes", "@anthropic-ai/claude-code", "--version"],
                capture_output=True, timeout=30, shell=False
            )
            if result.returncode == 0:
                self.claude_bin = "npx @anthropic-ai/claude-code"

    def is_available(self) -> bool:
        """Check if Claude Code is available."""
        if self.claude_bin and Path(self.claude_bin.replace(".cmd", "")).exists():
            return True
        # Check if npx works
        result = subprocess.run(
            ["npx", "--yes", "@anthropic-ai/claude-code", "--help"],
            capture_output=True, timeout=30, shell=False
        )
        return result.returncode == 0

    # ─── HTTP MCP Mode (preferred) ───────────────────────────────────────

    def _call_mcp_http(self, messages: List[Dict], tools: List[Dict],
                       max_tokens: int = 4096) -> ClaudeResponse:
        """
        Call Claude Code via its MCP HTTP server.
        Claude Code exposes an MCP endpoint when running.
        """
        # Claude Code runs an MCP server on a local port
        # The port is usually 8765 or found via claude config
        mcp_port = int(os.environ.get("CLAUDE_MCP_PORT", "8765"))
        mcp_url = f"http://127.0.0.1:{mcp_port}/tools/call"

        payload = {
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            mcp_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return ClaudeResponse(
                    content=result.get("content", ""),
                    tool_calls=result.get("tool_calls", []),
                    usage=result.get("usage", {}),
                )
        except urllib.error.URLError as e:
            return ClaudeResponse(
                content="",
                error=f"MCP HTTP not available: {e}. Is Claude Code running with MCP server?",
            )

    # ─── Subprocess STDIO Mode ───────────────────────────────────────────

    def _start_subprocess(self):
        """Start Claude Code as a subprocess in MCP mode."""
        if self._process:
            return

        cmd = self.claude_bin.split() if isinstance(self.claude_bin, str) else [self.claude_bin]
        cmd = [self.claude_bin] if isinstance(self.claude_bin, str) else self.claude_bin

        # Check if it's a .cmd file (Windows batch)
        if self.claude_bin and self.claude_bin.endswith(".cmd"):
            shell = True
        else:
            shell = False

        self._process = subprocess.Popen(
            cmd + ["--mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.workspace_root,
            shell=shell,
            env={**os.environ, "CODEX_WORKSPACE": self.workspace_root},
        )

        self._reader_running = True
        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()

        # Wait for init
        time.sleep(2)

    def _read_output(self):
        """Read output from Claude Code subprocess in background thread."""
        while self._reader_running and self._process:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                self._output_buffer += line.decode("utf-8", errors="replace")
                # Try to parse complete JSON-RPC messages
                while "\n" in self._output_buffer:
                    msg_end = self._output_buffer.index("\n")
                    msg_str = self._output_buffer[:msg_end]
                    self._output_buffer = self._output_buffer[msg_end + 1:]
                    try:
                        msg = json.loads(msg_str)
                        self._handle_message(msg)
                    except json.JSONDecodeError:
                        continue
            except Exception:
                break

    def _handle_message(self, msg: Dict):
        """Handle incoming JSON-RPC message."""
        msg_id = msg.get("id")
        if msg_id and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if "result" in msg:
                future.set_result(msg["result"])
            elif "error" in msg:
                future.set_exception(Exception(str(msg["error"])))

    def _send_request(self, method: str, params: Dict) -> Any:
        """Send a JSON-RPC request and wait for response."""
        if not self._process:
            self._start_subprocess()

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.Future()
        self._pending[self._request_id] = future

        request_str = json.dumps(request) + "\n"
        self._process.stdin.write(request_str.encode("utf-8"))
        self._process.stdin.flush()

        try:
            return future.result(timeout=120)
        except FuturesTimeoutError:
            return {"error": "Request timed out"}

    def _stop_subprocess(self):
        """Stop the Claude Code subprocess."""
        self._reader_running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    # ─── High-Level Chat Interface ────────────────────────────────────────

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None,
             model: str = "claude-sonnet-4-6", max_tokens: int = 4096) -> ClaudeResponse:
        """
        Send a chat message to Claude Code and get a response.

        This is the main interface - mirrors the OpenAI chat format.

        Args:
            messages: List of {"role": "...", "content": "..."} messages
            tools: List of tool definitions (MCP tool format)
            model: Model to use
            max_tokens: Max output tokens

        Returns:
            ClaudeResponse with content, tool_calls, usage, error
        """
        # Try HTTP MCP first
        if tools is not None:
            return self._call_mcp_http(messages, tools, max_tokens)

        # Fall back to subprocess mode
        if not self._process:
            try:
                self._start_subprocess()
            except Exception as e:
                return ClaudeResponse(
                    content="",
                    error=f"Could not start Claude Code: {e}",
                )

        # Build Claude Code prompt from messages
        prompt = self._build_prompt(messages)

        try:
            result = self._send_request("complete", {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
                "tools": tools or [],
            })

            if "error" in result:
                return ClaudeResponse(content="", error=str(result["error"]))

            return ClaudeResponse(
                content=result.get("content", ""),
                tool_calls=result.get("tool_calls", []),
                usage=result.get("usage", {}),
            )
        except Exception as e:
            return ClaudeResponse(content="", error=str(e))

    def _build_prompt(self, messages: List[Dict]) -> str:
        """Build a plain text prompt from message history."""
        lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text":
                            parts.append(c.get("text", ""))
                        elif c.get("type") == "tool_result":
                            parts.append(f"[Tool: {c.get('tool_use_id', 'unknown')} -> {c.get('content', '')}]")
                content = " ".join(parts)
            lines.append(f"## {role.upper()}\n{content}")
        return "\n\n".join(lines)

    # ─── Tool Execution via MCP ──────────────────────────────────────────

    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        """Execute a tool via Claude Code's MCP."""
        if not self._process:
            return {"success": False, "error": "Claude Code not running"}

        try:
            result = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools from Claude Code."""
        if not self._process:
            return []

        try:
            result = self._send_request("tools/list", {})
            return result.get("tools", [])
        except Exception:
            return []

    def close(self):
        """Clean up resources."""
        self._stop_subprocess()
        self._executor.shutdown(wait=False)

    def __del__(self):
        self.close()


# ─── Integration: Use Claude Code as Loop Provider ─────────────────────────

class ClaudeCodeLoopProvider:
    """
    Use Claude Code as the LLM provider for Codex-Local's auto-loop.
    This gives the loop access to Claude Code's full tool ecosystem.

    Usage:
        provider = ClaudeCodeLoopProvider()
        loop = CodexLoop()  # from runtime.loop
        loop.set_provider(provider)
        result = asyncio.run(loop.run_task("Build me a web scraper"))
    """

    def __init__(self):
        self.bridge = ClaudeCodeBridge()
        self.is_available = self.bridge.is_available()

    def chat(self, messages: List[Dict], tools: Optional[List[Dict]] = None,
             model: str = "claude-sonnet-4-6", max_tokens: int = 4096) -> ClaudeResponse:
        """Chat with Claude Code (blocking)."""
        return self.bridge.chat(messages, tools, model, max_tokens)

    async def chat_async(self, messages: List[Dict], tools: Optional[List[Dict]] = None,
                         model: str = "claude-sonnet-4-6", max_tokens: int = 4096) -> ClaudeResponse:
        """Chat with Claude Code (async)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.bridge.chat,
            messages, tools, model, max_tokens
        )

    def close(self):
        self.bridge.close()


# ─── MCP Server Wrapper ────────────────────────────────────────────────────

class ClaudeCodeMCPServer:
    """
    Expose Claude Code as an MCP server that Codex-Local can connect to.
    This wraps Claude Code's tools as MCP tool definitions.

    Claude Code already speaks MCP! We just need to bridge it properly.
    """

    def __init__(self, port: int = 8765):
        self.port = port
        self.bridge = ClaudeCodeBridge()
        self._running = False

    def run_stdio(self):
        """Run as STDIO MCP server (for Claude Code's MCP protocol)."""
        import sys

        def send_response(msg_id, result):
            print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}), flush=True)

        def send_error(msg_id, code, message):
            print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}), flush=True)

        # Initialize
        print(json.dumps({
            "jsonrpc": "2.0",
            "id": None,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codex-local", "version": "1.0.0"},
            }
        }), flush=True)

        for line in sys.stdin:
            try:
                msg = json.loads(line.strip())
                method = msg.get("method", "")
                msg_id = msg.get("id")

                if method == "tools/list":
                    tools = self.bridge.list_tools()
                    send_response(msg_id, {"tools": tools})

                elif method == "tools/call":
                    params = msg.get("params", {})
                    name = params.get("name", "")
                    args = params.get("arguments", {})
                    result = self.bridge.execute_tool(name, args)
                    send_response(msg_id, {"content": [{"type": "text", "text": json.dumps(result)}]})

                elif method == "initialize":
                    send_response(msg_id, {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "codex-local", "version": "1.0.0"},
                    })

                else:
                    send_error(msg_id, -32601, f"Unknown method: {method}")

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)


# ─── Quick Test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bridge = ClaudeCodeBridge()

    print(f"Claude Code available: {bridge.is_available()}")

    if bridge.is_available():
        # Test simple chat
        response = bridge.chat([
            {"role": "user", "content": "What is 2+2? Just answer briefly."}
        ])
        print(f"Response: {response.content}")
        print(f"Error: {response.error}")
    else:
        print("Claude Code not found. Install with: npm i -g @anthropic-ai/claude-code")