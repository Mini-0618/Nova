"""
Codex-Local LSP (Language Server Protocol) Integration
Provides: code completion, go-to-definition, diagnostics, hover, find references.
Supports: Python (pyright), JavaScript/TypeScript (tsserver).
Uses subprocess-based LSP communication via JSON-RPC over stdio.
"""

import os
import sys
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, Future
from concurrent.futures._base import TimeoutError as FuturesTimeoutError

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ─── LSP Types ─────────────────────────────────────────────────────────────

@dataclass
class LSPCompletion:
    label: str
    kind: str          # "function" / "method" / "class" / "variable" / "module"
    detail: str        # type signature
    insert_text: str   # snippet e.g. "func(${1:arg})"
    documentation: str = ""
    range: Optional[Dict] = None


@dataclass
class LSPDiagnostic:
    severity: str       # "error" / "warning" / "information" / "hint"
    message: str
    file: str
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None


@dataclass
class LSPLocation:
    file: str
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    uri: str = ""


# ─── LSP Message Protocol ────────────────────────────────────────────────

class LSPProtocol:
    """Minimal LSP JSON-RPC protocol handler."""

    def __init__(self, process: subprocess.Popen):
        self.process = process
        self.process.stdin = getattr(process.stdin, 'buffer', process.stdin)
        self.process.stdout = getattr(process.stdout, 'buffer', process.stdout)
        self._id = 0
        self._lock = threading.Lock()
        self._pending: Dict[int, Future] = {}
        self._reader_running = False
        self._reader_thread: Optional[threading.Thread] = None
        self._content_length = 0
        self._buffer = b""

    def _next_message(self) -> Optional[Dict]:
        """Read one LSP message (blocking)."""
        # Read headers
        headers = {}
        while True:
            line = self.process.stdout.readline()
            if not line:
                return None
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                break
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

        content_length = int(headers.get("content-length", 0))
        if content_length == 0:
            return None

        body = b""
        while len(body) < content_length:
            chunk = self.process.stdout.read(content_length - len(body))
            if not chunk:
                return None
            body += chunk

        return json.loads(body.decode("utf-8", errors="replace"))

    def _send(self, method: str, params: Dict, id: int = None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if id is not None:
            msg["id"] = id
        body = json.dumps(msg, ensure_ascii=False)
        header = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n"
        self.process.stdin.write(header.encode("utf-8"))
        self.process.stdin.write(body.encode("utf-8"))
        self.process.stdin.flush()

    def send_request(self, method: str, params: Dict, timeout: float = 10) -> Dict:
        """Send a request and wait for response."""
        with self._lock:
            self._id += 1
            req_id = self._id
            future = Future()
            self._pending[req_id] = future
            self._send(method, params, req_id)

        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            with self._lock:
                self._pending.pop(req_id, None)
            return {"error": f"Request {method} timed out after {timeout}s"}

    def send_notification(self, method: str, params: Dict):
        """Fire and forget."""
        self._send(method, params)

    def handle_response(self, msg: Dict):
        rid = msg.get("id")
        if rid and rid in self._pending:
            future = self._pending.pop(rid)
            if "result" in msg:
                future.set_result(msg["result"])
            elif "error" in msg:
                future.set_exception(Exception(str(msg["error"])))


# ─── Base LSP Server ─────────────────────────────────────────────────────

class LSPServer:
    """
    Base LSP server wrapper.
    Handles lifecycle: initialize, shutdown, and provides common LSP methods.

    Usage:
        server = PyrightLSP("D:/project")
        server.start()
        completions = server.completions("src/main.py", line=10, col=5, text="imp")
        diagnostics = server.diagnostics("src/main.py")
        definitions = server.goto_definition("src/main.py", line=10, col=5)
        server.stop()
    """

    LANGUAGE_SERVER_COMMAND = ""  # Override in subclass
    LANGUAGE_ID = ""             # Override in subclass

    def __init__(self, workspace_root: str, python_path: str = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.python_path = python_path or sys.executable
        self.process: Optional[subprocess.Popen] = None
        self.protocol: Optional[LSPProtocol] = None
        self._started = False
        self._initialization_done = False

    def _build_command(self) -> List[str]:
        """Build the LSP server command. Override in subclass."""
        return []

    def start(self):
        """Start the LSP server process."""
        if self._started:
            return

        cmd = self._build_command()
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.workspace_root),
            env={**os.environ, "PYTHONPATH": str(self.workspace_root)},
        )

        self.protocol = LSPProtocol(self.process)

        # Send initialize
        init_result = self.protocol.send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": str(self.workspace_root).replace("\\", "/"),
            "rootPath": str(self.workspace_root),
            "capabilities": {
                "textDocument": {
                    "completion": {"dynamicRegistration": True},
                    "hover": {"dynamicRegistration": True},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "diagnostic": {"dynamicRegistration": True},
                },
                "workspace": {"symbol": {"dynamicRegistration": True}},
            },
        }, timeout=30)

        self._initialization_done = True

        # Send initialized notification
        self.protocol.send_notification("initialized", {})

        self._started = True

    def stop(self):
        if self.process:
            try:
                self.protocol.send_notification("shutdown", {})
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
            self._started = False
            self._initialization_done = False

    def is_running(self) -> bool:
        return self._started and self._initialization_done and self.process and self.process.poll() is None

    def _open_doc(self, file_path: str):
        """Send textDocument/didOpen notification."""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        uri = str(path).replace("\\", "/")
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""

        self.protocol.send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": uri,
                "languageId": self.LANGUAGE_ID,
                "version": 1,
                "text": content,
            }
        })

    def completions(self, file_path: str, line: int, col: int, text: str = "") -> List[LSPCompletion]:
        """Get code completions at a position."""
        if not self.is_running():
            return []
        self._open_doc(file_path)

        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        uri = str(path).replace("\\", "/")

        result = self.protocol.send_request("textDocument/completion", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": col},
        }, timeout=5)

        if isinstance(result, dict) and "result" in result:
            result = result["result"]

        completions = []
        items = result if isinstance(result, list) else (result.get("items", []) if isinstance(result, dict) else [])

        kind_map = {
            1: "text", 2: "method", 3: "function", 4: "constructor",
            5: "field", 6: "variable", 7: "class", 8: "interface",
            9: "module", 10: "property", 11: "unit", 12: "value",
            13: "enum", 14: "keyword", 15: "snippet", 16: "color",
            17: "file", 18: "reference", 19: "folder", 20: "enumMember",
            21: "constant", 22: "struct", 23: "event", 24: "operator",
            25: "typeParameter",
        }

        for item in items[:50]:
            if isinstance(item, dict):
                completions.append(LSPCompletion(
                    label=item.get("label", ""),
                    kind=kind_map.get(item.get("kind", 0), "unknown"),
                    detail=item.get("detail", ""),
                    insert_text=item.get("insertText") or item.get("label", ""),
                    documentation=item.get("documentation", ""),
                    range=item.get("textEdit", {}).get("range") if item.get("textEdit") else None,
                ))

        return completions

    def goto_definition(self, file_path: str, line: int, col: int) -> List[LSPLocation]:
        """Go to definition of symbol at position."""
        if not self.is_running():
            return []
        self._open_doc(file_path)

        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        uri = str(path).replace("\\", "/")

        result = self.protocol.send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": col},
        }, timeout=5)

        result = result.get("result", result) if isinstance(result, dict) else result
        if not isinstance(result, list):
            result = [result] if result else []

        locations = []
        for r in result:
            if isinstance(r, dict):
                loc = r.get("uri", "")
                pos = r.get("range", {}).get("start", {})
                locations.append(LSPLocation(
                    file=Path(loc.replace("file://", "").replace("/", "\\")).name if loc else "",
                    line=(pos.get("line", 0) + 1),
                    column=pos.get("character", 0),
                    end_line=(r.get("range", {}).get("end", {}).get("line", 0) + 1) if r.get("range", {}).get("end") else None,
                    end_column=(r.get("range", {}).get("end", {}).get("character", 0)) if r.get("range", {}).get("end") else None,
                    uri=loc,
                ))
        return locations

    def diagnostics(self, file_path: str) -> List[LSPDiagnostic]:
        """Get all diagnostics (errors/warnings) for a file."""
        if not self.is_running():
            return []
        self._open_doc(file_path)

        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        uri = str(path).replace("\\", "/")

        # Trigger a document sync
        self.protocol.send_notification("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": 2},
            "contentChanges": [{"text": path.read_text("utf-8", errors="replace")}],
        })

        time.sleep(0.5)  # Allow server to process

        # Get diagnostics via workspace diagnostics
        result = self.protocol.send_request("textDocument/diagnostic", {
            "textDocument": {"uri": uri},
        }, timeout=10)

        diagnostics = []
        items = result if isinstance(result, list) else (result.get("items", []) if isinstance(result, dict) else [])

        severity_map = {1: "hint", 2: "information", 3: "warning", 4: "error"}

        for item in items:
            if isinstance(item, dict):
                pos = item.get("range", {}).get("start", {})
                end_pos = item.get("range", {}).get("end", {})
                diagnostics.append(LSPDiagnostic(
                    severity=severity_map.get(item.get("severity", 3), "warning"),
                    message=item.get("message", ""),
                    file=str(path),
                    line=(pos.get("line", 0) + 1),
                    column=pos.get("character", 0),
                    end_line=(end_pos.get("line", 0) + 1) if end_pos else None,
                    end_column=end_pos.get("character", 0) if end_pos else None,
                ))

        return diagnostics

    def hover(self, file_path: str, line: int, col: int) -> str:
        """Get hover info at position."""
        if not self.is_running():
            return ""
        self._open_doc(file_path)

        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        uri = str(path).replace("\\", "/")

        result = self.protocol.send_request("textDocument/hover", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": col},
        }, timeout=5)

        result = result.get("result", result) if isinstance(result, dict) else result
        if isinstance(result, dict):
            contents = result.get("contents", "")
            if isinstance(contents, dict):
                return contents.get("value", str(contents))
            return str(contents)
        return ""

    def find_references(self, file_path: str, line: int, col: int) -> List[LSPLocation]:
        """Find all references to symbol at position."""
        if not self.is_running():
            return []
        self._open_doc(file_path)

        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace_root / path
        uri = str(path).replace("\\", "/")

        result = self.protocol.send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line - 1, "character": col},
            "context": {"includeDeclaration": True},
        }, timeout=10)

        result = result.get("result", result) if isinstance(result, dict) else (result or [])

        locations = []
        for r in (result if isinstance(result, list) else []):
            if isinstance(r, dict):
                loc = r.get("uri", "")
                pos = r.get("range", {}).get("start", {})
                locations.append(LSPLocation(
                    file=Path(loc.replace("file://", "").replace("/", "\\")).name if loc else "",
                    line=(pos.get("line", 0) + 1),
                    column=pos.get("character", 0),
                    uri=loc,
                ))
        return locations


# ─── Pyright (Python LSP) ──────────────────────────────────────────────

class PyrightLSP(LSPServer):
    """Pyright LSP server for Python."""

    LANGUAGE_ID = "python"
    LANGUAGE_SERVER_COMMAND = "pyright"  # pip install pyright

    def _build_command(self) -> List[str]:
        # Find pyright
        pyright = self._find_pyright()
        if not pyright:
            raise RuntimeError("pyright not found. Install: pip install pyright")
        return [str(pyright), "--server"]

    def _find_pyright(self) -> Optional[Path]:
        for base in [
            self.python_path.replace("\\Scripts", "\\Scripts").replace("\\Scripts", "\\Scripts"),
            Path(sys.prefix) / "Scripts" / "pyright.exe",
            Path(sys.prefix) / "bin" / "pyright",
        ]:
            p = Path(str(base).replace("\\Scripts", "").replace("\\bin", "") / "Scripts" / "pyright.exe")
            if p.exists():
                return p
            p2 = Path(str(base).replace("\\Scripts", "") / "bin" / "pyright")
            if p2.exists():
                return p2
        # Try PATH
        import shutil
        path = shutil.which("pyright")
        if path:
            return Path(path)
        return None


# ─── TS/JS LSP (typescript-language-server) ─────────────────────────────

class TSServerLSP(LSPServer):
    """TypeScript language server for JS/TS."""

    LANGUAGE_ID = "typescript"
    LANGUAGE_SERVER_COMMAND = "typescript-language-server"  # npm install -g typescript-language-server

    def _build_command(self) -> List[str]:
        import shutil
        tsserver = shutil.which("typescript-language-server") or shutil.which("tsserver")
        if not tsserver:
            raise RuntimeError("typescript-language-server not found. Install: npm i -g typescript-language-server")
        return [tsserver, "--stdio"]


# ─── Tool wrapper ──────────────────────────────────────────────────────

def lsp_tool(operation: str, file_path: str = "", line: int = 1, col: int = 0,
             workspace: str = None, language: str = "python", **kwargs) -> Dict[str, Any]:
    """
    LSP tool entry point for executor.
    """
    ws = workspace or os.environ.get("CODEX_WORKSPACE", "D:/")

    try:
        if language == "python":
            server = PyrightLSP(ws)
        else:
            server = TSServerLSP(ws)

        server.start()

        if operation == "completions":
            comps = server.completions(file_path, line, col)
            return {
                "success": True,
                "completions": [
                    {
                        "label": c.label,
                        "kind": c.kind,
                        "detail": c.detail,
                        "insert_text": c.insert_text,
                        "documentation": c.documentation,
                    }
                    for c in comps
                ],
                "count": len(comps),
            }

        elif operation == "diagnostics":
            diags = server.diagnostics(file_path)
            return {
                "success": True,
                "diagnostics": [
                    {
                        "severity": d.severity,
                        "message": d.message,
                        "line": d.line,
                        "column": d.column,
                    }
                    for d in diags
                ],
                "count": len(diags),
            }

        elif operation == "goto":
            defs = server.goto_definition(file_path, line, col)
            return {
                "success": True,
                "definitions": [
                    {"file": d.file, "line": d.line, "column": d.column}
                    for d in defs
                ],
            }

        elif operation == "hover":
            info = server.hover(file_path, line, col)
            return {"success": True, "hover": info}

        elif operation == "references":
            refs = server.find_references(file_path, line, col)
            return {
                "success": True,
                "references": [
                    {"file": r.file, "line": r.line, "column": r.column}
                    for r in refs
                ],
                "count": len(refs),
            }

        else:
            return {"success": False, "error": f"Unknown LSP operation: {operation}"}

    except Exception as e:
        return {"success": False, "error": str(e)}

    finally:
        try:
            server.stop()
        except Exception:
            pass


# ─── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    ws = sys.argv[2] if len(sys.argv) > 2 else "D:/codex-local"
    file = sys.argv[3] if len(sys.argv) > 3 else "D:/codex-local/tools/executor.py"
    lang = sys.argv[4] if len(sys.argv) > 4 else "python"

    print(f"LSP test: ws={ws}, file={file}, lang={lang}")

    try:
        server = PyrightLSP(ws) if lang == "python" else TSServerLSP(ws)
        server.start()
        print(f"Pyright started: {server.is_running()}")

        # Test diagnostics
        diags = server.diagnostics(file)
        print(f"Diagnostics: {len(diags)} issues")
        for d in diags[:5]:
            print(f"  [{d.severity}] {d.message} at {d.line}:{d.column}")

        server.stop()

    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()