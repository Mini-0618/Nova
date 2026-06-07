"""
Browser MCP Server
Provides browser control tools via MCP protocol.
Works with Chrome DevTools Protocol (CDP) or via system automation.
"""

import os
import sys
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from .server import MCPServer, spawn_stdio_server


class BrowserMCPServer(MCPServer):
    def __init__(self):
        self._chrome_port = int(os.environ.get("CODEX_CHROME_PORT", "9222"))
        self._cdp_ws_url: Optional[str] = None
        super().__init__("browser", "1.0.0")

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "browser_navigate",
                "description": "Navigate to a URL in the browser",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "new_tab": {"type": "boolean"},
                    },
                    "required": ["url"],
                },
            },
            {
                "name": "browser_snapshot",
                "description": "Take a screenshot of current page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                },
            },
            {
                "name": "browser_click",
                "description": "Click an element by CSS selector",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                    },
                    "required": ["selector"],
                },
            },
            {
                "name": "browser_type",
                "description": "Type text into an element or at current position",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "selector": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "browser_press",
                "description": "Press a keyboard key",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "ctrl": {"type": "boolean"},
                        "shift": {"type": "boolean"},
                    },
                    "required": ["key"],
                },
            },
            {
                "name": "browser_evaluate",
                "description": "Execute JavaScript in the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string"},
                    },
                    "required": ["script"],
                },
            },
            {
                "name": "browser_screenshot",
                "description": "Save a screenshot to file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "full_page": {"type": "boolean"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "browser_get_text",
                "description": "Get text content of an element",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                    },
                    "required": ["selector"],
                },
            },
        ]

    def execute_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        method = getattr(self, f"_cmd_{tool_name}", None)
        if method:
            return method(arguments)
        return {"error": f"Unknown tool: {tool_name}"}

    def _get_cdp_connection(self) -> Optional[Any]:
        """Get CDP WebSocket connection. Returns None if not available."""
        try:
            import websocket
            if self._cdp_ws_url is None:
                # Discover Chrome via CDP HTTP
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

    def _cmd_browser_navigate(self, args: Dict) -> Dict:
        url = args["url"]
        try:
            # Try Chrome CDP
            ws = self._get_cdp_connection()
            if ws:
                tab_id = json.loads(
                    urllib.request.urlopen(
                        f"http://localhost:{self._chrome_port}/json/new?{url}", timeout=5
                    ).read()
                ).get("id")
                ws.close()
                return {"success": True, "url": url, "method": "cdp"}
            # Fallback: PowerShell automation
            script = f'''
$shell = New-Object -ComObject Shell.Application
$windows = $shell.Windows()
foreach ($win in $windows) {{
    if ($win.Name -eq "Chrome") {{
        $win.Navigate("{url}")
        break
    }}
}}
'''
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True, timeout=10,
            )
            return {"success": result.returncode == 0, "url": url, "method": "com"}
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}

    def _cmd_browser_snapshot(self, args: Dict) -> Dict:
        return self._cmd_browser_screenshot(args)

    def _cmd_browser_screenshot(self, args: Dict) -> Dict:
        path = args.get("path", f"D:/codex-local/screenshots/snap_{int(time.time())}.png")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            # Try maim/grim on WSL or PowerShell
            result = subprocess.run(
                ["powershell", "-Command",
                 f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bitmap.Save("{path.replace("/", "\\")}")
$graphics.Dispose()
$bitmap.Dispose()
'''],
                capture_output=True, timeout=15,
            )
            return {"success": result.returncode == 0, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _cmd_browser_click(self, args: Dict) -> Dict:
        selector = args["selector"]
        script = f'''
$script = @"
var el = document.querySelector('{selector}');
if (el) {{ el.click(); }} else {{ throw 'Element not found'; }}
"@
'''
        return self._run_cdp_script(script)

    def _cmd_browser_type(self, args: Dict) -> Dict:
        text = args["text"].replace("'", "\\'")
        selector = args.get("selector", "body")
        script = f'''
var el = document.querySelector('{selector}');
if (el) {{ el.value = '{text}'; el.dispatchEvent(new Event('input')); }} else {{ throw 'Element not found'; }}
'''
        return self._run_cdp_script(script)

    def _cmd_browser_press(self, args: Dict) -> Dict:
        key = args["key"]
        ctrl = args.get("ctrl", False)
        shift = args.get("shift", False)
        modifiers = 0
        if ctrl: modifiers |= 2
        if shift: modifiers |= 1
        script = f"document.body.dispatchEvent(new KeyboardEvent('keydown', {{key: '{key}', modifiers: {modifiers}}}));"
        return self._run_cdp_script(script)

    def _cmd_browser_evaluate(self, args: Dict) -> Dict:
        script = args["script"]
        return self._run_cdp_script(script)

    def _run_cdp_script(self, script: str) -> Dict:
        try:
            ws = self._get_cdp_connection()
            if ws:
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": script}}))
                resp = ws.recv()
                ws.close()
                result = json.loads(resp)
                return {"success": True, "result": result.get("result", {})}
            return {"success": False, "error": "Browser not connected via CDP"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _cmd_browser_get_text(self, args: Dict) -> Dict:
        selector = args["selector"].replace("'", "\\'")
        script = f'''
var el = document.querySelector('{selector}');
el ? el.textContent : '';
'''
        return self._run_cdp_script(script)


if __name__ == "__main__":
    server = BrowserMCPServer()
    spawn_stdio_server(server)