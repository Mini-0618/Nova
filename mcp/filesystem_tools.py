"""
Filesystem Tools Module (ToolModule wrapper)
Wraps existing filesystem functionality into the unified ToolModule interface.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from .server import ToolModule


WORKSPACE_ROOT = os.environ.get("CODEX_WORKSPACE", "D:/")


class FileSystemTools(ToolModule):
    """Filesystem tools as MCP tools."""

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        return Path(WORKSPACE_ROOT) / p

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "Read",
                "description": "Read file contents (with optional offset/limit for large files)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to file"},
                        "limit": {"type": "integer", "description": "Max lines to read"},
                        "offset": {"type": "integer", "description": "Line offset to start from"},
                    },
                    "required": ["file_path"],
                },
                "handler": self._read,
            },
            {
                "name": "Write",
                "description": "Write content to a file (creates parent dirs if needed)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to file"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["file_path", "content"],
                },
                "handler": self._write,
            },
            {
                "name": "Edit",
                "description": "Edit a file by replacing old_string with new_string (first occurrence)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to file"},
                        "old_string": {"type": "string", "description": "Text to find"},
                        "new_string": {"type": "string", "description": "Replacement text"},
                    },
                    "required": ["file_path", "old_string", "new_string"],
                },
                "handler": self._edit,
            },
            {
                "name": "Glob",
                "description": "Find files matching a glob pattern",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern"},
                        "root": {"type": "string", "description": "Root directory"},
                    },
                    "required": ["pattern"],
                },
                "handler": self._glob,
            },
            {
                "name": "Bash",
                "description": "Execute a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to run"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
                        "cwd": {"type": "string", "description": "Working directory"},
                    },
                    "required": ["command"],
                },
                "handler": self._bash,
            },
            {
                "name": "Mkdir",
                "description": "Create a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path"},
                        "parents": {"type": "boolean", "description": "Create parent dirs (default: true)"},
                    },
                    "required": ["path"],
                },
                "handler": self._mkdir,
            },
            {
                "name": "Rm",
                "description": "Remove a file or directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to remove"},
                        "recursive": {"type": "boolean", "description": "Remove recursively"},
                    },
                    "required": ["path"],
                },
                "handler": self._rm,
            },
            {
                "name": "Cp",
                "description": "Copy file or directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "src": {"type": "string", "description": "Source path"},
                        "dst": {"type": "string", "description": "Destination path"},
                    },
                    "required": ["src", "dst"],
                },
                "handler": self._cp,
            },
            {
                "name": "Mv",
                "description": "Move/rename file or directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "src": {"type": "string", "description": "Source path"},
                        "dst": {"type": "string", "description": "Destination path"},
                    },
                    "required": ["src", "dst"],
                },
                "handler": self._mv,
            },
            {
                "name": "Stat",
                "description": "Get file/directory metadata (size, mtime, type)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to stat"},
                    },
                    "required": ["path"],
                },
                "handler": self._stat,
            },
        ]

    def _read(self, file_path: str, limit: int = None, offset: int = None) -> Dict:
        path = self._resolve(file_path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if offset is not None or limit is not None:
                lines = content.splitlines()
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

    def _write(self, file_path: str, content: str) -> Dict:
        path = self._resolve(file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"success": True, "file_path": str(path), "bytes": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _edit(self, file_path: str, old_string: str, new_string: str) -> Dict:
        path = self._resolve(file_path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            if old_string not in content:
                return {"success": False, "error": "old_string not found in file"}
            new = content.replace(old_string, new_string, 1)
            path.write_text(new, encoding="utf-8")
            return {"success": True, "file_path": str(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _glob(self, pattern: str, root: str = None) -> Dict:
        r = Path(root) if root else Path(WORKSPACE_ROOT)
        try:
            files = [str(p) for p in r.glob(pattern)]
            return {"success": True, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "files": [], "error": str(e)}

    def _bash(self, command: str, timeout: int = 30, cwd: str = None) -> Dict:
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True,
                timeout=timeout, cwd=cwd or WORKSPACE_ROOT,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout}s", "exit_code": -1}
        except Exception as e:
            return {"success": False, "error": str(e), "exit_code": -1}

    def _mkdir(self, path: str, parents: bool = True) -> Dict:
        p = self._resolve(path)
        try:
            p.mkdir(parents=parents, exist_ok=True)
            return {"success": True, "path": str(p)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _rm(self, path: str, recursive: bool = False) -> Dict:
        p = self._resolve(path)
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _cp(self, src: str, dst: str) -> Dict:
        s = self._resolve(src)
        d = self._resolve(dst)
        try:
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _mv(self, src: str, dst: str) -> Dict:
        s = self._resolve(src)
        d = self._resolve(dst)
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _stat(self, path: str) -> Dict:
        p = self._resolve(path)
        try:
            st = p.stat()
            return {
                "success": True,
                "path": str(p),
                "size": st.st_size,
                "mtime": st.st_mtime,
                "is_file": p.is_file(),
                "is_dir": p.is_dir(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
