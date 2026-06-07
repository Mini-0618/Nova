"""
Codex-Local MCP Server Framework
Supports both STDIO (for Claude Code integration) and HTTP modes.
Each server implements a set of tools that Claude Code can call.
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from abc import ABC, abstractmethod


class MCPServer(ABC):
    """
    Base class for MCP servers.
    Subclass and implement get_tools().
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools = self.get_tools()

    @abstractmethod
    def get_tools(self) -> List[Dict]:
        """Return list of tool definitions."""
        pass

    @abstractmethod
    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        """Execute a tool by name with given arguments."""
        pass

    # ─── STDIO Protocol ─────────────────────────────────────────────────────

    async def run_stdio(self):
        """
        Run as STDIO MCP server (for Claude Code integration).
        JSON-RPC-like protocol over stdin/stdout.
        """
        while True:
            line = await asyncio.get_event_loop().run_in_executor(sys.stdin, sys.stdin.readline)
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
                    result = {"tools": self.tools}
                    await self._send_response(msg_id, result)

                elif method == "tools/call":
                    tool_name = params.get("name", "")
                    tool_args = params.get("arguments", {})
                    try:
                        exec_result = self.execute_tool(tool_name, tool_args)
                        result = {
                            "content": [{"type": "text", "text": json.dumps(exec_result, ensure_ascii=False)}],
                        }
                        await self._send_response(msg_id, result)
                    except Exception as e:
                        error = {"type": "text", "text": f"Error: {e}"}
                        result = {"content": [error], "isError": True}
                        await self._send_response(msg_id, result)

                else:
                    await self._send_error(msg_id, -32601, f"Unknown method: {method}")

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Server error: {e}", file=sys.stderr)
                await self._send_error(None, -32603, str(e))

    async def _send_response(self, msg_id, result):
        if msg_id is None:
            return
        resp = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        print(json.dumps(resp), flush=True)

    async def _send_error(self, msg_id, code: int, message: str):
        if msg_id is None:
            return
        resp = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
        print(json.dumps(resp), flush=True)


# ─── Tool Decorator ─────────────────────────────────────────────────────────

class ToolRegistry:
    """Simple registry for MCP tools."""

    def __init__(self):
        self._tools: Dict[str, Callable] = {}

    def register(self, name: str, description: str, parameters: Dict, func: Callable):
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "func": func,
        }

    def list_tools(self) -> List[Dict]:
        return [
            {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            }
            for name, spec in self._tools.items()
        ]

    def call(self, name: str, arguments: Dict) -> Any:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        return self._tools[name]["func"](**arguments)


# ─── HTTP MCP Server ─────────────────────────────────────────────────────────

class HTTPServer:
    """
    Lightweight HTTP server wrapping an MCP server.
    Allows external programs to call tools via HTTP POST.
    """

    def __init__(self, mcp_server: MCPServer, host: str = "127.0.0.1", port: int = 8765):
        self.mcp_server = mcp_server
        self.host = host
        self.port = port
        self._running = False

    async def handler(self, scope, receive, send):
        """Handle HTTP requests."""
        if scope["path"] == "/tools/list" and scope["method"] == "GET":
            await self._json_response(send, 200, {"tools": self.mcp_server.tools})
        elif scope["path"] == "/tools/call" and scope["method"] == "POST":
            body = await self._read_body(receive, scope)
            try:
                params = json.loads(body) if body else {}
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                result = self.mcp_server.execute_tool(tool_name, tool_args)
                await self._json_response(send, 200, result)
            except Exception as e:
                await self._json_response(send, 500, {"error": str(e)})
        else:
            await self._json_response(send, 404, {"error": "not found"})

    async def _read_body(self, receive, scope) -> str:
        body = b""
        while True:
            event = await receive()
            if event["type"] == "http.request":
                body += event.get("body", b"")
                if not event.get("more_body"):
                    break
        return body.decode("utf-8", errors="replace")

    async def _json_response(self, send, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [[b"content-type", b"application/json"]],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    async def run(self):
        import asyncio
        import socket
        server = await asyncio.start_server(self._handle, self.host, self.port)
        self._running = True
        print(f"[mcp] HTTP server running at http://{self.host}:{self.port}")
        async with server:
            await server.serve_forever()

    async def _handle(self, reader, writer):
        scope = {"path": "/", "method": "GET"}
        raw = await reader.read(4096)
        if raw:
            lines = raw.decode("utf-8", errors="replace").split("\r\n")
            if lines:
                parts = lines[0].split(" ")
                if len(parts) >= 2:
                    scope["method"] = parts[0]
                    scope["path"] = parts[1]

        class FakeReceive:
            async def receive(self):
                return {"type": "http.request", "body": b"", "more_body": False}

        class FakeSend:
            data = b""
            async def __call__(self, msg):
                if msg["type"] == "http.response.body":
                    self.data += msg.get("body", b"")

        send = FakeSend()
        await self.handler(scope, FakeReceive(), send)
        writer.write(send.data)
        await writer.drain()
        writer.close()


# ─── Spawn helpers ───────────────────────────────────────────────────────────

def spawn_stdio_server(server: MCPServer):
    """Run an MCP server using STDIO mode."""
    asyncio.run(server.run_stdio())


def spawn_subprocess(command: List[str], mcp_server: MCPServer):
    """Spawn a subprocess running an MCP server."""
    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


if __name__ == "__main__":
    # Example: run a basic server
    class HelloServer(MCPServer):
        def get_tools(self):
            return [{
                "name": "hello",
                "description": "Say hello",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            }]

        def execute_tool(self, tool_name, arguments):
            return {"message": f"Hello, {arguments.get('name', 'world')}!"}

    server = HelloServer("hello")
    print("Starting STDIO server...", file=sys.stderr)
    asyncio.run(server.run_stdio())