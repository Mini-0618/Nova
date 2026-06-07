"""
Sandbox MCP Server
Provides sandboxed code execution tools via MCP protocol.
Supports: sandbox_exec, DebugRun, DebugPytest, DebugExplain
"""

import os
import sys
import json
import importlib.util
from pathlib import Path
from typing import Dict, Any, List

# Try relative import first (when used as package), fall back to absolute
try:
    from .server import MCPServer, spawn_stdio_server
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from server import MCPServer, spawn_stdio_server

# Path to runtime/sandbox.py (avoids name collision with this file)
_RUNTIME_SANDBOX = str(Path(__file__).parent.parent / "runtime" / "sandbox.py")


def _load_runtime_sandbox():
    """Load runtime/sandbox.py as a module, bypassing the name conflict with this file."""
    if "runtime_sandbox" not in sys.modules:
        spec = importlib.util.spec_from_file_location("runtime_sandbox", _RUNTIME_SANDBOX)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["runtime_sandbox"] = mod
    return sys.modules["runtime_sandbox"]


class SandboxMCPServer(MCPServer):
    def __init__(self):
        super().__init__("sandbox", "1.0.0")
        self._sandbox = None

    def _get_sandbox(self):
        if self._sandbox is None:
            rt = _load_runtime_sandbox()
            self._sandbox = rt.Sandbox()
        return self._sandbox

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "sandbox_exec",
                "description": "Execute code in an isolated sandbox environment",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code to execute"
                        },
                        "language": {
                            "type": "string",
                            "enum": ["python", "javascript", "shell", "bash"],
                            "description": "Programming language"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Execution timeout in seconds (default: 30)"
                        },
                    },
                    "required": ["code", "language"],
                },
            },
            {
                "name": "DebugRun",
                "description": "Execute code with full debug information: stack trace, frames with local variables",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Execution timeout in seconds (default: 30)"
                        },
                    },
                    "required": ["code"],
                },
            },
            {
                "name": "DebugPytest",
                "description": "Run pytest on a file or directory with detailed failure information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to test file or directory"
                        },
                        "test_name": {
                            "type": "string",
                            "description": "Specific test name to run (optional)"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Execution timeout in seconds (default: 60)"
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "DebugExplain",
                "description": "Analyze error output and provide explanation with suggestions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "error_output": {
                            "type": "string",
                            "description": "Error output to analyze"
                        },
                        "stack_trace": {
                            "type": "string",
                            "description": "Optional stack trace for more context"
                        },
                    },
                    "required": ["error_output"],
                },
            },
        ]

    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        if tool_name == "sandbox_exec":
            return self._sandbox_exec(arguments)
        elif tool_name == "DebugRun":
            return self._debug_run(arguments)
        elif tool_name == "DebugPytest":
            return self._debug_pytest(arguments)
        elif tool_name == "DebugExplain":
            return self._debug_explain(arguments)
        return {"error": f"Unknown tool: {tool_name}"}

    def _sandbox_exec(self, args: Dict) -> Dict:
        sandbox = self._get_sandbox()
        code = args["code"]
        language = args.get("language", "python")
        timeout = args.get("timeout", 30)

        # Temporarily override timeout
        original_timeout = sandbox.timeout_sec
        sandbox.timeout_sec = timeout
        try:
            result = sandbox.execute(code, language)
            return result.to_dict()
        finally:
            sandbox.timeout_sec = original_timeout

    def _debug_run(self, args: Dict) -> Dict:
        sandbox = self._get_sandbox()
        code = args["code"]
        timeout = args.get("timeout", 30)

        result = sandbox.debug_run(code, timeout=timeout)
        return result.to_dict()

    def _debug_pytest(self, args: Dict) -> Dict:
        sandbox = self._get_sandbox()
        path = args["path"]
        test_name = args.get("test_name")
        timeout = args.get("timeout", 60)

        result = sandbox.debug_pytest(path, test_name, timeout)
        return result.to_dict()

    def _debug_explain(self, args: Dict) -> Dict:
        rt = _load_runtime_sandbox()
        error_output = args["error_output"]
        stack_trace = args.get("stack_trace")

        return rt.debug_explain(error_output, stack_trace)


if __name__ == "__main__":
    server = SandboxMCPServer()
    spawn_stdio_server(server)
