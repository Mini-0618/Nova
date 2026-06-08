"""
Search Tools Module
Provides code search: grep, glob, find references, list functions.
"""

import os
import re
import ast
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from .server import ToolModule


class SearchTools(ToolModule):
    """Code search tools as MCP tools."""

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "grep_search",
                "description": "Search file contents using regex pattern (like ripgrep)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory or file to search"},
                        "pattern": {"type": "string", "description": "Regex pattern to search for"},
                        "glob": {"type": "string", "description": "File glob filter (e.g. '*.py')"},
                    },
                    "required": ["path", "pattern"],
                },
                "handler": self._grep_search,
            },
            {
                "name": "glob_search",
                "description": "Find files matching a glob pattern",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Root directory to search"},
                        "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')"},
                    },
                    "required": ["path", "pattern"],
                },
                "handler": self._glob_search,
            },
            {
                "name": "find_references",
                "description": "Find all references to a symbol (function/class/variable name) in a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory to search"},
                        "symbol": {"type": "string", "description": "Symbol name to find references for"},
                    },
                    "required": ["path", "symbol"],
                },
                "handler": self._find_references,
            },
            {
                "name": "list_functions",
                "description": "List all functions and classes defined in a Python file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string", "description": "Python file to analyze"},
                    },
                    "required": ["file"],
                },
                "handler": self._list_functions,
            },
        ]

    def _grep_search(self, path: str, pattern: str, glob: str = None) -> Dict:
        """Search file contents using regex."""
        try:
            target = Path(path)
            if not target.exists():
                return {"success": False, "error": f"Path not found: {path}"}

            regex = re.compile(pattern, re.IGNORECASE)
            matches = []

            if target.is_file():
                files = [target]
            else:
                if glob:
                    files = list(target.rglob(glob))
                else:
                    files = [f for f in target.rglob("*") if f.is_file() and f.suffix in {
                        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
                        ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".sh", ".bash",
                        ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".md", ".txt",
                        ".html", ".css", ".scss", ".sql", ".xml",
                    }]

            for fp in files[:500]:  # Cap at 500 files
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            matches.append({
                                "file": str(fp),
                                "line": i,
                                "content": line.rstrip()[:300],
                            })
                            if len(matches) >= 200:
                                return {"success": True, "matches": matches, "count": len(matches), "truncated": True}
                except (OSError, UnicodeDecodeError):
                    continue

            return {"success": True, "matches": matches, "count": len(matches)}
        except re.error as e:
            return {"success": False, "error": f"Invalid regex: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _glob_search(self, path: str, pattern: str) -> Dict:
        """Find files matching glob pattern."""
        try:
            root = Path(path)
            if not root.exists():
                return {"success": False, "error": f"Path not found: {path}"}
            files = [str(p) for p in root.glob(pattern) if p.is_file()]
            return {"success": True, "files": files[:500], "count": len(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _find_references(self, path: str, symbol: str) -> Dict:
        """Find all references to a symbol."""
        try:
            # Use word-boundary regex for exact symbol match
            pattern = rf"\b{re.escape(symbol)}\b"
            return self._grep_search(path, pattern)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _list_functions(self, file: str) -> Dict:
        """List functions and classes in a Python file using AST."""
        try:
            fp = Path(file)
            if not fp.exists():
                return {"success": False, "error": f"File not found: {file}"}
            if fp.suffix != ".py":
                return {"success": False, "error": "Only .py files are supported for list_functions"}

            source = fp.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(fp))

            items = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    items.append({
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "args": [a.arg for a in node.args.args],
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    })
                elif isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            methods.append(item.name)
                    items.append({
                        "type": "class",
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods,
                    })

            return {"success": True, "items": items, "count": len(items)}
        except SyntaxError as e:
            return {"success": False, "error": f"Syntax error: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
