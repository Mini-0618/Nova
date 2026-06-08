"""
Process Tools Module
Provides process management: list, kill, info.
"""

import os
import signal
import subprocess
from typing import Dict, Any, List

from .server import ToolModule


class ProcessTools(ToolModule):
    """Process management tools as MCP tools."""

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "process_list",
                "description": "List running processes, optionally filtered by name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filter": {"type": "string", "description": "Filter by process name (substring match)"},
                    },
                },
                "handler": self._process_list,
            },
            {
                "name": "process_kill",
                "description": "Terminate a process by PID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pid": {"type": "integer", "description": "Process ID to kill"},
                        "force": {"type": "boolean", "description": "Force kill (SIGKILL instead of SIGTERM)"},
                    },
                    "required": ["pid"],
                },
                "handler": self._process_kill,
            },
            {
                "name": "process_info",
                "description": "Get detailed info about a process by PID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pid": {"type": "integer", "description": "Process ID"},
                    },
                    "required": ["pid"],
                },
                "handler": self._process_info,
            },
        ]

    def _process_list(self, filter: str = None) -> Dict:
        try:
            # Use tasklist on Windows, ps on Unix
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FO", "CSV", "/NH"],
                    capture_output=True, timeout=10, text=True,
                )
                processes = []
                for line in result.stdout.strip().splitlines():
                    parts = line.strip().strip('"').split('","')
                    if len(parts) >= 5:
                        name, pid, session, session_num, mem = parts[0], parts[1], parts[2], parts[3], parts[4]
                        if filter and filter.lower() not in name.lower():
                            continue
                        processes.append({
                            "name": name,
                            "pid": int(pid),
                            "session": session,
                            "memory": mem,
                        })
                    if len(processes) >= 200:
                        break
                return {"success": True, "processes": processes, "count": len(processes)}
            else:
                result = subprocess.run(
                    ["ps", "aux", "--no-headers"],
                    capture_output=True, timeout=10, text=True,
                )
                processes = []
                for line in result.stdout.strip().splitlines():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        name = parts[10].split("/")[-1].split()[0]
                        if filter and filter.lower() not in name.lower():
                            continue
                        processes.append({
                            "name": name,
                            "pid": int(parts[1]),
                            "cpu": parts[2],
                            "mem": parts[3],
                            "command": parts[10][:200],
                        })
                    if len(processes) >= 200:
                        break
                return {"success": True, "processes": processes, "count": len(processes)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _process_kill(self, pid: int, force: bool = False) -> Dict:
        try:
            if os.name == "nt":
                cmd = ["taskkill", "/PID", str(pid)]
                if force:
                    cmd.append("/F")
                result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                }
            else:
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.kill(pid, sig)
                return {"success": True, "pid": pid, "signal": sig.name}
        except ProcessLookupError:
            return {"success": False, "error": f"Process {pid} not found"}
        except PermissionError:
            return {"success": False, "error": f"Permission denied to kill process {pid}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _process_info(self, pid: int) -> Dict:
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/V"],
                    capture_output=True, timeout=10, text=True,
                )
                lines = [l for l in result.stdout.strip().splitlines() if "PID" not in l]
                if not lines:
                    return {"success": False, "error": f"Process {pid} not found"}
                parts = lines[0].strip().strip('"').split('","')
                return {
                    "success": True,
                    "pid": pid,
                    "name": parts[0] if parts else "unknown",
                    "raw": lines[0][:500],
                }
            else:
                result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "pid,ppid,user,%cpu,%mem,vsz,rss,stat,start,time,command", "--no-headers"],
                    capture_output=True, timeout=10, text=True,
                )
                if not result.stdout.strip():
                    return {"success": False, "error": f"Process {pid} not found"}
                parts = result.stdout.strip().split(None, 10)
                return {
                    "success": True,
                    "pid": int(parts[0]),
                    "ppid": int(parts[1]),
                    "user": parts[2],
                    "cpu_percent": parts[3],
                    "mem_percent": parts[4],
                    "vsz": parts[5],
                    "rss": parts[6],
                    "state": parts[7],
                    "start": parts[8],
                    "time": parts[9],
                    "command": parts[10][:500] if len(parts) > 10 else "",
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
