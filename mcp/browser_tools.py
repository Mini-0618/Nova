"""
Browser Tools Module (ToolModule wrapper)
Wraps existing browser control functionality into the unified ToolModule interface.
"""

import os
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from .server import ToolModule


class BrowserTools(ToolModule):
    """Browser control tools as MCP tools."""

    def __init__(self):
        self._chrome_port = int(os.environ.get("CODEX_CHROME_PORT", "9222"))
        self._cdp_ws_url: Optional[str] = None

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "browser_navigate",
                "description": "Navigate to a URL in the browser",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to navigate to"},
                    },
                    "required": ["url"],
                },
                "handler": self._navigate,
            },
            {
                "name": "browser_screenshot",
                "description": "Take a screenshot of the current page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Output file path"},
                    },
                },
                "handler": self._screenshot,
            },
            {
                "name": "browser_click",
                "description": "Click an element by CSS selector",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector"},
                    },
                    "required": ["selector"],
                },
                "handler": self._click,
            },
            {
                "name": "browser_type",
                "description": "Type text into an element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"},
                        "selector": {"type": "string", "description": "CSS selector of target element"},
                    },
                    "required": ["text"],
                },
                "handler": self._type,
            },
            {
                "name": "browser_evaluate",
                "description": "Execute JavaScript in the browser page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "JavaScript to execute"},
                    },
                    "required": ["script"],
                },
                "handler": self._evaluate,
            },
            {
                "name": "browser_get_text",
                "description": "Get text content of an element by CSS selector",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector"},
                    },
                    "required": ["selector"],
                },
                "handler": self._get_text,
            },
        ]

    def _get_cdp_connection(self):
        """Get CDP WebSocket connection. Returns None if not available."""
        try:
            import websocket
            if self._cdp_ws_url is None:
                import urllib.request
                resp = urllib.request.urlopen(
                    f"http://localhost:{self._chrome_port}/json", timeout=5
                )
                tabs = json.loads(resp.read().decode())
                if tabs:
                    ws_url = tabs[0].get("webSocketDebuggerUrl")
                    if ws_url:
                        self._cdp_ws_url = ws_url
                        ws = websocket.create_connection(ws_url, timeout=10)
                        return ws
            return None
        except Exception:
            return None

    def _run_cdp_script(self, script: str) -> Dict:
        try:
            ws = self._get_cdp_connection()
            if ws:
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": script}}))
                resp = ws.recv()
                ws.close()
                result = json.loads(resp)
                return {"success": True, "result": result.get("result", {})}
            return {"success": False, "error": "Browser not connected via CDP. Start Chrome with --remote-debugging-port=9222"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _navigate(self, url: str) -> Dict:
        try:
            import urllib.request
            ws = self._get_cdp_connection()
            if ws:
                ws.send(json.dumps({
                    "id": 1, "method": "Page.navigate", "params": {"url": url}
                }))
                resp = ws.recv()
                ws.close()
                return {"success": True, "url": url, "method": "cdp"}
            # Fallback: open in default browser
            import webbrowser
            webbrowser.open(url)
            return {"success": True, "url": url, "method": "webbrowser"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _screenshot(self, path: str = None) -> Dict:
        out = path or f"D:/codex-local/screenshots/snap_{int(time.time())}.png"
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["powershell", "-Command", f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bitmap.Save("{out.replace("/", "\\")}")
$graphics.Dispose()
$bitmap.Dispose()
'''],
                capture_output=True, timeout=15,
            )
            return {"success": result.returncode == 0, "path": out}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _click(self, selector: str) -> Dict:
        script = f"document.querySelector('{selector}')?.click()"
        return self._run_cdp_script(script)

    def _type(self, text: str, selector: str = "body") -> Dict:
        safe_text = text.replace("'", "\\'")
        script = f"var el=document.querySelector('{selector}'); if(el){{el.value='{safe_text}';el.dispatchEvent(new Event('input'))}}"
        return self._run_cdp_script(script)

    def _evaluate(self, script: str) -> Dict:
        return self._run_cdp_script(script)

    def _get_text(self, selector: str) -> Dict:
        script = f"document.querySelector('{selector}')?.textContent || ''"
        return self._run_cdp_script(script)
