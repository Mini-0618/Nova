"""
System Tools Module
Provides system information: OS/CPU/memory info, disk usage, environment variables.
"""

import os
import platform
import shutil
from typing import Dict, Any, List

from .server import ToolModule


class SystemTools(ToolModule):
    """System information tools as MCP tools."""

    def get_tools(self) -> List[Dict]:
        return [
            {
                "name": "system_info",
                "description": "Get OS, CPU, and memory information",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
                "handler": self._system_info,
            },
            {
                "name": "disk_usage",
                "description": "Get disk usage information for a path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to check disk usage for"},
                    },
                },
                "handler": self._disk_usage,
            },
            {
                "name": "env_get",
                "description": "Get the value of an environment variable",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Environment variable name"},
                    },
                    "required": ["key"],
                },
                "handler": self._env_get,
            },
            {
                "name": "env_set",
                "description": "Set an environment variable (for current process)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Environment variable name"},
                        "value": {"type": "string", "description": "Value to set"},
                    },
                    "required": ["key", "value"],
                },
                "handler": self._env_set,
            },
        ]

    def _system_info(self) -> Dict:
        try:
            import multiprocessing
            info = {
                "success": True,
                "os": platform.system(),
                "os_release": platform.release(),
                "os_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor() or platform.machine(),
                "python_version": platform.python_version(),
                "cpu_count": multiprocessing.cpu_count(),
                "hostname": platform.node(),
            }
            # Memory info
            if os.name == "nt":
                try:
                    import ctypes
                    class MEMORYSTATUSEX(ctypes.Structure):
                        _fields_ = [
                            ("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                        ]
                    mem = MEMORYSTATUSEX()
                    mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
                    info["memory_total_gb"] = round(mem.ullTotalPhys / (1024**3), 2)
                    info["memory_available_gb"] = round(mem.ullAvailPhys / (1024**3), 2)
                    info["memory_load_percent"] = mem.dwMemoryLoad
                except Exception:
                    pass
            else:
                try:
                    with open("/proc/meminfo") as f:
                        meminfo = {}
                        for line in f:
                            parts = line.split(":")
                            if len(parts) == 2:
                                key = parts[0].strip()
                                val = parts[1].strip().split()[0]
                                meminfo[key] = int(val)
                    if "MemTotal" in meminfo:
                        info["memory_total_gb"] = round(meminfo["MemTotal"] / (1024**2), 2)
                    if "MemAvailable" in meminfo:
                        info["memory_available_gb"] = round(meminfo["MemAvailable"] / (1024**2), 2)
                except Exception:
                    pass
            return info
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _disk_usage(self, path: str = None) -> Dict:
        try:
            target = path or "/"
            if os.name == "nt" and not path:
                target = "C:\\"
            usage = shutil.disk_usage(target)
            return {
                "success": True,
                "path": target,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "used_percent": round(usage.used / usage.total * 100, 1),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _env_get(self, key: str) -> Dict:
        try:
            value = os.environ.get(key)
            if value is None:
                return {"success": False, "error": f"Environment variable '{key}' not set"}
            return {"success": True, "key": key, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _env_set(self, key: str, value: str) -> Dict:
        try:
            os.environ[key] = value
            return {"success": True, "key": key, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}
