"""
Sandbox Tools Module (ToolModule wrapper)
Wraps existing sandbox execution functionality into the unified ToolModule interface.
"""

import os
import sys
import json
import importlib.util
from pathlib import Path
from typing import Dict, Any, List

from .server import ToolModule

# Path to runtime/sandbox.py (avoids name collision with this file)
_RUNTIME_SANDBOX = str(Path(__file__).parent.parent / "runtime" / "sandbox.py")


def _load_runtime_sandbox():
    """Load runtime/sandbox.py as a module, bypassing the name conflict."""
    if "runtime_sandbox" not in sys.modules:
        spec = importlib.util.spec_from_file_location("runtime_sandbox", _RUNTIME_SANDBOX)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["runtime_sandbox"] = mod
    return sys.modules["runtime_sandbox"]


class SandboxTools(ToolModule):
    """Sandbox code execution tools as MCP tools."""

    def __init__(self):
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
                        "code": {"type": "string", "description": "Code to execute"},
                        "language": {
                            "type": "string",
                            "enum": ["python", "javascript", "shell", "bash"],
                            "description": "Programming language",
                        },
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
                    },
                    "required": ["code", "language"],
                },
                "handler": self._sandbox_exec,
            },
            {
                "name": "DebugRun",
                "description": "Execute Python code with full debug info (stack trace, local variables)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
                    },
                    "required": ["code"],
                },
                "handler": self._debug_run,
            },
            {
                "name": "DebugPytest",
                "description": "Run pytest on a file/directory with detailed failure info",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Test file or directory"},
                        "test_name": {"type": "string", "description": "Specific test name (optional)"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)"},
                    },
                    "required": ["path"],
                },
                "handler": self._debug_pytest,
            },
            {
                "name": "DebugExplain",
                "description": "Analyze error output and provide explanation with fix suggestions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "error_output": {"type": "string", "description": "Error output to analyze"},
                        "stack_trace": {"type": "string", "description": "Optional stack trace"},
                    },
                    "required": ["error_output"],
                },
                "handler": self._debug_explain,
            },
        ]

    def _sandbox_exec(self, code: str, language: str = "python", timeout: int = 30) -> Dict:
        try:
            sandbox = self._get_sandbox()
            original_timeout = sandbox.timeout_sec
            sandbox.timeout_sec = timeout
            try:
                result = sandbox.execute(code, language)
                return result.to_dict()
            finally:
                sandbox.timeout_sec = original_timeout
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _debug_run(self, code: str, timeout: int = 30) -> Dict:
        try:
            sandbox = self._get_sandbox()
            result = sandbox.debug_run(code, timeout=timeout)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _debug_pytest(self, path: str, test_name: str = None, timeout: int = 60) -> Dict:
        try:
            sandbox = self._get_sandbox()
            result = sandbox.debug_pytest(path, test_name, timeout)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _debug_explain(self, error_output: str, stack_trace: str = None) -> Dict:
        try:
            rt = _load_runtime_sandbox()
            return rt.debug_explain(error_output, stack_trace)
        except Exception as e:
            return {"success": False, "error": str(e)}
