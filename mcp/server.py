"""
Codex-Local MCP Unified Server
Registers all tool modules and exposes them via STDIO/HTTP protocols.
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from abc import ABC, abstractmethod


# ─── Tool Module ABC ────────────────────────────────────────────────────────

class ToolModule(ABC):
    """Base class for all MCP tool modules. Each module exposes tools via get_tools()."""

    @abstractmethod
    def get_tools(self) -> List[Dict]:
        """
        Return list of tool definitions. Each dict must contain:
          - name: str
          - description: str
          - parameters: dict (JSON Schema)
          - handler: Callable(**kwargs) -> dict
        """
        pass


# ─── Unified MCP Server ─────────────────────────────────────────────────────

class CodexMCPServer:
    """
    Unified MCP Server that registers all tool modules.
    Supports STDIO (for Claude Code) and HTTP modes.
    """

    def __init__(self):
        self.name = "codex-local"
        self.version = "2.0.0"
        self.tools: Dict[str, Dict] = {}
        self._modules: List[ToolModule] = []
        self._auto_register()

    def _auto_register(self):
        """Register all built-in tool modules."""
        from .filesystem_tools import FileSystemTools
        from .browser_tools import BrowserTools
        from .sandbox_tools import SandboxTools
        from .git_tools import GitTools
        from .search_tools import SearchTools
        from .db_tools import DBTools
        from .http_tools import HttpTools
        from .process_tools import ProcessTools
        from .system_tools import SystemTools

        for module_cls in [
            FileSystemTools,
            GitTools,
            SearchTools,
            DBTools,
            HttpTools,
            ProcessTools,
            SystemTools,
            BrowserTools,
            SandboxTools,
        ]:
            self.register_module(module_cls())

    def register_module(self, module: ToolModule):
        """Register a tool module, adding all its tools."""
        self._modules.append(module)
        for tool in module.get_tools():
            name = tool["name"]
            if name in self.tools:
                print(f"[mcp] Warning: duplicate tool '{name}', overwriting", file=sys.stderr)
            self.tools[name] = tool

    def list_tools(self) -> List[Dict]:
        """List all registered tools (name + description + parameters)."""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "parameters": t.get("parameters", {}),
            }
            for t in self.tools.values()
        ]

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool by name with arguments. Returns result dict."""
        if name not in self.tools:
            return {"success": False, "error": f"Unknown tool: {name}"}
        handler = self.tools[name]["handler"]
        try:
            result = handler(**args)
            if not isinstance(result, dict):
                result = {"result": result}
            return result
        except TypeError as e:
            return {"success": False, "error": f"Invalid arguments for '{name}': {e}"}
        except Exception as e:
            return {"success": False, "error": f"Tool '{name}' failed: {e}"}

    def get_tool_count(self) -> int:
        return len(self.tools)

    def get_module_count(self) -> int:
        return len(self._modules)

    # ─── STDIO Protocol ─────────────────────────────────────────────────────

    async def run_stdio(self):
        """
        Run as STDIO MCP server (for Claude Code integration).
        JSON-RPC 2.0 protocol over stdin/stdout.
        """
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            try:
                msg = json.loads(line.strip())
                method = msg.get("method", "")
                msg_id = msg.get("id")
                params = msg.get("params", {})

                if method == "initialize":
                    result = {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": self.name, "version": self.version},
                    }
                    await self._send_response(msg_id, result)

                elif method == "tools/list":
                    tools = self.list_tools()
                    await self._send_response(msg_id, {"tools": tools})

                elif method == "tools/call":
                    tool_name = params.get("name", "")
                    tool_args = params.get("arguments", {})
                    exec_result = self.call_tool(tool_name, tool_args)
                    is_error = not exec_result.get("success", True) if isinstance(exec_result, dict) else False
                    result = {
                        "content": [{"type": "text", "text": json.dumps(exec_result, ensure_ascii=False, default=str)}],
                    }
                    if is_error:
                        result["isError"] = True
                    await self._send_response(msg_id, result)

                else:
                    await self._send_error(msg_id, -32601, f"Unknown method: {method}")

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[mcp] Server error: {e}", file=sys.stderr)
                await self._send_error(None, -32603, str(e))

    async def _send_response(self, msg_id, result):
        if msg_id is None:
            return
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        print(json.dumps(resp, default=str), flush=True)

    async def _send_error(self, msg_id, code: int, message: str):
        if msg_id is None:
            return
        resp = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
        print(json.dumps(resp), flush=True)


# ─── HTTP MCP Server ─────────────────────────────────────────────────────────

class HTTPServer:
    """
    Lightweight HTTP server wrapping CodexMCPServer.
    POST /tools/call, GET /tools/list, GET /tools/count.
    """

    def __init__(self, server: CodexMCPServer, host: str = "127.0.0.1", port: int = 8765):
        self.server = server
        self.host = host
        self.port = port

    async def run(self):
        srv = await asyncio.start_server(self._handle, self.host, self.port)
        print(f"[mcp] HTTP server running at http://{self.host}:{self.port}")
        async with srv:
            await srv.serve_forever()

    async def _handle(self, reader, writer):
        raw = await reader.read(8192)
        if not raw:
            writer.close()
            return

        lines = raw.decode("utf-8", errors="replace").split("\r\n")
        method, path = "GET", "/"
        if lines:
            parts = lines[0].split(" ")
            if len(parts) >= 2:
                method, path = parts[0], parts[1]

        # Extract body for POST
        body_str = ""
        if method == "POST":
            sep = raw.find(b"\r\n\r\n")
            if sep >= 0:
                body_str = raw[sep + 4:].decode("utf-8", errors="replace")

        status, data = 404, {"error": "not found"}

        if path == "/tools/list" and method == "GET":
            status, data = 200, {"tools": self.server.list_tools()}
        elif path == "/tools/count" and method == "GET":
            status, data = 200, {"count": self.server.get_tool_count(), "modules": self.server.get_module_count()}
        elif path == "/tools/call" and method == "POST":
            try:
                params = json.loads(body_str) if body_str else {}
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                result = self.server.call_tool(tool_name, tool_args)
                status, data = 200, result
            except Exception as e:
                status, data = 500, {"error": str(e)}

        resp_body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        header = f"HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(resp_body)}\r\n\r\n"
        writer.write(header.encode("utf-8") + resp_body)
        await writer.drain()
        writer.close()


# ─── Spawn helpers ───────────────────────────────────────────────────────────

def spawn_stdio_server(server: CodexMCPServer):
    """Run a CodexMCPServer using STDIO mode."""
    asyncio.run(server.run_stdio())


def create_server() -> CodexMCPServer:
    """Factory: create a fully-loaded CodexMCPServer."""
    return CodexMCPServer()


# Backward compatibility aliases
MCPServer = CodexMCPServer


if __name__ == "__main__":
    server = create_server()
    print(f"[mcp] Starting STDIO server | {server.get_tool_count()} tools, {server.get_module_count()} modules", file=sys.stderr)
    spawn_stdio_server(server)
