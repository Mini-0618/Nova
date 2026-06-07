"""
Codex-Local Copilot Protocol Bridge
Implements the GitHub Copilot inline completion protocol.
Provides ghost-text style suggestions the same way Copilot does.
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@dataclass
class CopilotSuggestion:
    text: str                    # The completion text to insert
    display_text: str            # What to show in ghost (may include prefix/suffix)
    source: str = "copilot"     # "copilot" | "agent"
    priority: int = 0           # Higher = more preferred
    metadata: Dict[str, Any] = None


# ─── Protocol Implementation ─────────────────────────────────

class CopilotProtocol:
    """
    Implements the GitHub Copilot extension protocol for VS Code integration.
    This lets Codex-Local provide inline completions via the same API Copilot uses.

    Protocol:
    - POST /v1/Completions  - Get completion suggestions
    - POST /v1/Engage/Re engage - Start engagement tracking
    - GET  /v1/Health      - Health check
    """

    LANGUAGE_IDS = {
        "python": "python",
        "javascript": "javascript",
        "typescript": "typescript",
        "java": "java",
        "go": "go",
        "rust": "rust",
        "cpp": "cpp",
        "c": "c",
        "csharp": "csharp",
        "php": "php",
        "ruby": "ruby",
        "swift": "swift",
        "kotlin": "kotlin",
        "sql": "sql",
        "shell": "shell",
        "yaml": "yaml",
        "json": "json",
        "toml": "toml",
        "markdown": "markdown",
    }

    def __init__(self, brain=None, model: str = "deepseek-coder"):
        self.brain = brain
        self.model = model
        self._running = False

    def get_completions(
        self,
        text: str,
        language: str,
        cursor: int,
        file_path: str = "",
        max_tokens: int = 200,
    ) -> List[CopilotSuggestion]:
        """
        Get inline completions for the given text context.
        This is the core method that VS Code extension calls.
        """
        if not self.brain:
            return []

        # Build a prompt from context
        prompt = self._build_completion_prompt(text, language, file_path)

        try:
            response = self.brain.think(prompt, max_tokens=max_tokens)
            if response and response.strip():
                return [
                    CopilotSuggestion(
                        text=response.strip(),
                        display_text=response.strip(),
                        source="codex-local",
                        priority=90,
                    )
                ]
        except Exception:
            pass

        return []

    def _build_completion_prompt(self, text: str, language: str, file_path: str) -> str:
        """Build a prompt for inline completion."""
        lang = self.LANGUAGE_IDS.get(language, language)

        prompt = f"""Complete the following {lang} code.
Only return the completion, nothing else. No explanations.

Code so far:
{text}

Completion:"""

        return prompt


# ─── HTTP Server (for VS Code Extension) ──────────────────────────

class CopilotHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_json(self, status: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path == "/v1/health":
            self.send_json(200, {"status": "ok", "service": "codex-local-copilot"})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/v1/completions":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                req = json.loads(body)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "invalid JSON"})
                return

            text = req.get("text", "")
            language = req.get("language", "python")
            cursor = req.get("cursor", 0)
            file_path = req.get("file", "")
            max_tokens = req.get("max_tokens", 200)

            server: CopilotServer = self.server
            suggestions = server.copilot.get_completions(
                text=text,
                language=language,
                cursor=cursor,
                file_path=file_path,
                max_tokens=max_tokens,
            )

            self.send_json(200, {
                "completions": [
                    {
                        "text": s.text,
                        "displayText": s.display_text,
                        "source": s.source,
                        "priority": s.priority,
                    }
                    for s in suggestions
                ]
            })
            return

        self.send_json(404, {"error": "not found"})


class CopilotServer:
    """
    HTTP server that speaks the Copilot protocol.
    VS Code extension connects to this to get inline completions.

    Usage:
        server = CopilotServer(brain=my_brain)
        server.run(port=7890)
    """

    def __init__(self, brain=None, model: str = "deepseek-coder"):
        from runtime.brain import AgentBrain
        self.brain = brain or AgentBrain(model=model)
        self.copilot = CopilotProtocol(self.brain, model)
        self.port = 7890
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def run(self, port: int = None):
        port = port or self.port
        self.port = port

        class Handler(CopilotHandler):
            pass
        Handler.__qualname__ = "CopilotHandler"

        self.server = HTTPServer(("127.0.0.1", port), Handler)
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True
        print(f"[codex-local] Copilot server running on http://127.0.0.1:{port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self._running = False

    def get_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


# ─── VS Code Extension Config ─────────────────────────────────

def get_extension_config(port: int = 7890) -> dict:
    """
    Returns the VS Code settings.json snippet to add to enable this Copilot bridge.
    User adds this to their VS Code settings.json.
    """
    return {
        "github.copilot.enable": {
            "@exten": "github.copilot"
        },
        "github.copilot.advanced": {
            "inlineSuggestionThreshold": 200,
        },
        "github.copilot.server": f"http://127.0.0.1:{port}",
    }


# ─── Tool wrapper ─────────────────────────────────────────────

def copilot_tool(operation: str, text: str = "", language: str = "python",
                file_path: str = "", **kwargs) -> Dict[str, Any]:
    """
    Copilot protocol tool for executor.
    """
    try:
        if operation == "completions":
            from runtime.brain import AgentBrain
            brain = AgentBrain(model=kwargs.get("model", "deepseek-chat"))
            copilot = CopilotProtocol(brain)
            suggestions = copilot.get_completions(
                text=text,
                language=language,
                file_path=file_path,
                max_tokens=kwargs.get("max_tokens", 200),
            )
            return {
                "success": True,
                "completions": [
                    {"text": s.text, "source": s.source, "priority": s.priority}
                    for s in suggestions
                ],
                "count": len(suggestions),
            }

        elif operation == "start_server":
            server = CopilotServer()
            server.run(port=kwargs.get("port", 7890))
            return {
                "success": True,
                "url": server.get_url(),
                "message": "Server started. Add to VS Code settings to use.",
            }

        elif operation == "extension_config":
            return {
                "success": True,
                "config": get_extension_config(kwargs.get("port", 7890)),
            }

        else:
            return {"success": False, "error": f"Unknown operation: {operation}"}

    except Exception as e:
        import traceback; traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print("Copilot Protocol Bridge")
    print("Start server: python copilot_bridge.py serve")
    print("Get completions: python copilot_bridge.py complete <filepath> <language>")