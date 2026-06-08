"""
HTTP Tools Module
Provides HTTP request tools: GET, POST, download.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode

from .server import ToolModule


class HttpTools(ToolModule):
    """HTTP request tools as MCP tools."""

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "http_get",
                "description": "Send an HTTP GET request and return the response",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to fetch"},
                        "headers": {"type": "object", "description": "Optional HTTP headers"},
                    },
                    "required": ["url"],
                },
                "handler": self._http_get,
            },
            {
                "name": "http_post",
                "description": "Send an HTTP POST request with JSON body",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to post to"},
                        "data": {"type": "object", "description": "JSON body data"},
                        "headers": {"type": "object", "description": "Optional HTTP headers"},
                    },
                    "required": ["url", "data"],
                },
                "handler": self._http_post,
            },
            {
                "name": "http_download",
                "description": "Download a file from a URL to a local path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to download from"},
                        "output_path": {"type": "string", "description": "Local file path to save to"},
                    },
                    "required": ["url", "output_path"],
                },
                "handler": self._http_download,
            },
        ]

    def _http_get(self, url: str, headers: Dict = None) -> Dict:
        try:
            req = Request(url, method="GET")
            req.add_header("User-Agent", "codex-local/2.0")
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)

            with urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                # Try JSON parse
                try:
                    data = json.loads(body)
                    return {"success": True, "status": resp.status, "data": data}
                except json.JSONDecodeError:
                    return {"success": True, "status": resp.status, "text": body[:10000]}
        except HTTPError as e:
            return {"success": False, "status": e.code, "error": e.reason}
        except URLError as e:
            return {"success": False, "error": f"Connection failed: {e.reason}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _http_post(self, url: str, data: Dict, headers: Dict = None) -> Dict:
        try:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            req = Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("User-Agent", "codex-local/2.0")
            if headers:
                for k, v in headers.items():
                    req.add_header(k, v)

            with urlopen(req, timeout=30) as resp:
                resp_body = resp.read().decode("utf-8", errors="replace")
                try:
                    resp_data = json.loads(resp_body)
                    return {"success": True, "status": resp.status, "data": resp_data}
                except json.JSONDecodeError:
                    return {"success": True, "status": resp.status, "text": resp_body[:10000]}
        except HTTPError as e:
            return {"success": False, "status": e.code, "error": e.reason}
        except URLError as e:
            return {"success": False, "error": f"Connection failed: {e.reason}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _http_download(self, url: str, output_path: str) -> Dict:
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)

            req = Request(url)
            req.add_header("User-Agent", "codex-local/2.0")

            with urlopen(req, timeout=120) as resp:
                content = resp.read()
                out.write_bytes(content)
                return {
                    "success": True,
                    "path": str(out),
                    "size": len(content),
                    "content_type": resp.headers.get("Content-Type", ""),
                }
        except HTTPError as e:
            return {"success": False, "status": e.code, "error": e.reason}
        except URLError as e:
            return {"success": False, "error": f"Connection failed: {e.reason}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
