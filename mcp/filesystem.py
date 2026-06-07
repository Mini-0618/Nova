"""
Filesystem MCP Server
Provides filesystem tools via MCP protocol.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List
import json

from .server import MCPServer, spawn_stdio_server


WORKSPACE_ROOT = os.environ.get("CODEX_WORKSPACE", "D:/")


class FilesystemMCPServer(MCPServer):
    def __init__(self):
        super().__init__("filesystem", "1.0.0")

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "Read",
                "description": "Read file contents",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "limit": {"type": "integer"},
                        "offset": {"type": "integer"},
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "Write",
                "description": "Write content to file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["file_path", "content"],
                },
            },
            {
                "name": "Edit",
                "description": "Edit a file with old_string/new_string",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"},
                    },
                    "required": ["file_path", "old_string", "new_string"],
                },
            },
            {
                "name": "Glob",
                "description": "Glob pattern search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "root": {"type": "string"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "Bash",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                        "cwd": {"type": "string"},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "Mkdir",
                "description": "Create a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "parents": {"type": "boolean"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "Rm",
                "description": "Remove a file or directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "recursive": {"type": "boolean"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "Cp",
                "description": "Copy file or directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "src": {"type": "string"},
                        "dst": {"type": "string"},
                    },
                    "required": ["src", "dst"],
                },
            },
            {
                "name": "Mv",
                "description": "Move/rename file or directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "src": {"type": "string"},
                        "dst": {"type": "string"},
                    },
                    "required": ["src", "dst"],
                },
            },
            {
                "name": "Stat",
                "description": "Get file metadata",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
            },
        ]

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return Path(WORKSPACE_ROOT) / p

    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        if tool_name == "Read":
            return self._read(arguments)
        elif tool_name == "Write":
            return self._write(arguments)
        elif tool_name == "Edit":
            return self._edit(arguments)
        elif tool_name == "Glob":
            return self._glob(arguments)
        elif tool_name == "Bash":
            return self._bash(arguments)
        elif tool_name == "Mkdir":
            return self._mkdir(arguments)
        elif tool_name == "Rm":
            return self._rm(arguments)
        elif tool_name == "Cp":
            return self._cp(arguments)
        elif tool_name == "Mv":
            return self._mv(arguments)
        elif tool_name == "Stat":
            return self._stat(arguments)
        return {"error": f"Unknown tool: {tool_name}"}

    def _read(self, args: Dict) -> Dict:
        path = self._resolve(args["file_path"])
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if "limit" in args or "offset" in args:
                lines = content.splitlines()
                offset = args.get("offset", 0)
                limit = args.get("limit")
                if offset:
                    lines = lines[offset:]
                if limit:
                    lines = lines[:limit]
                content = "\n".join(lines)
            return {"success": True, "content": content, "file_path": str(path)}
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _write(self, args: Dict) -> Dict:
        path = self._resolve(args["file_path"])
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return {"success": True, "file_path": str(path), "bytes": len(args["content"])}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _edit(self, args: Dict) -> Dict:
        path = self._resolve(args["file_path"])
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if args["old_string"] not in content:
                return {"success": False, "error": "old_string not found"}
            new = content.replace(args["old_string"], args["new_string"], 1)
            path.write_text(new, encoding="utf-8")
            return {"success": True, "file_path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _glob(self, args: Dict) -> Dict:
        root = Path(args.get("root", WORKSPACE_ROOT))
        try:
            files = [str(p) for p in root.glob(args["pattern"])]
            return {"success": True, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "files": [], "error": str(e)}

    def _bash(self, args: Dict) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                args["command"],
                shell=True,
                capture_output=True,
                timeout=args.get("timeout", 30),
                cwd=args.get("cwd", WORKSPACE_ROOT),
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
                "exit_code": result.returncode,
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}

    def _mkdir(self, args: Dict) -> Dict:
        path = self._resolve(args["path"])
        try:
            path.mkdir(parents=args.get("parents", True), exist_ok=True)
            return {"success": True, "path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _rm(self, args: Dict) -> Dict:
        path = self._resolve(args["path"])
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _cp(self, args: Dict) -> Dict:
        src = self._resolve(args["src"])
        dst = self._resolve(args["dst"])
        try:
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _mv(self, args: Dict) -> Dict:
        src = self._resolve(args["src"])
        dst = self._resolve(args["dst"])
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _stat(self, args: Dict) -> Dict:
        path = self._resolve(args["path"])
        try:
            st = path.stat()
            return {
                "success": True,
                "path": str(path),
                "size": st.st_size,
                "mtime": st.st_mtime,
                "is_file": path.is_file(),
                "is_dir": path.is_dir(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


if __name__ == "__main__":
    server = FilesystemMCPServer()
    spawn_stdio_server(server)