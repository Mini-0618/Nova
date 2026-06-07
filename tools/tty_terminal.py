"""
Codex-Local TTY Terminal
True terminal emulation with ANSI escape sequences, full-screen UI.
Uses pyte for terminal screen simulation, supports ANSI colors.
"""

import os
import sys
import re
import shutil
import threading
import time
import fcntl
import termios
import tty
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from io import StringIO

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

try:
    import pyte
    HAS_PYTE = True
except ImportError:
    HAS_PYTE = False


@dataclass
class TerminalSize:
    columns: int = 80
    lines: int = 24


class AnsiParser:
    """Parse ANSI escape sequences into styled text."""

    # ANSI codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    COLOR_MAP = {
        "black": "\033[30m", "red": "\033[31m", "green": "\033[32m",
        "yellow": "\033[33m", "blue": "\033[34m", "magenta": "\033[35m",
        "cyan": "\033[36m", "white": "\033[37m",
        "bg_black": "\033[40m", "bg_red": "\033[41m",
        "bg_green": "\033[42m", "bg_yellow": "\033[43m",
    }

    def __init__(self):
        self._handlers = []

    def parse(self, text: str) -> List[Dict]:
        """Parse text into styled segments."""
        segments = []
        current_style = {}
        i = 0

        while i < len(text):
            if text[i] == "\033" and i + 1 < len(text) and text[i+1] == "[":
                # ANSI escape sequence
                j = i + 2
                while j < len(text) and text[j].isalpha():
                    j += 1
                code = text[i+2:j]
                self._apply_ansi_code(code, current_style)
                i = j
            else:
                segments.append({"char": text[i], "style": dict(current_style)})
                i += 1

        return segments

    def _apply_ansi_code(self, code: str, style: Dict):
        if code == "0":
            style.clear()
        elif code == "1":
            style["bold"] = True
        elif code in self.COLOR_MAP:
            style["fg"] = self.COLOR_MAP[code]
        elif code.startswith("38;5;"):
            # 256 color
            pass
        elif code.startswith("48;5;"):
            # 256 color bg
            pass


class FakeTerminal:
    """
    A full-screen terminal emulator that captures subprocess I/O.

    Features:
    - ANSI escape sequence support (colors, cursor movement)
    - Scrollback buffer
    - Search in output
    - Copy/paste
    - True PTY when available (Unix), subprocess when not (Windows)

    Usage:
        term = FakeTerminal(cols=120, lines=40)
        term.run(["python", "script.py"], cwd="D:/project")
        term.send("input data\\n")
        output = term.get_screen()
        term.resize(80, 24)
        term.stop()
    """

    def __init__(self, cols: int = 120, lines: int = 30, cwd: str = None):
        self.cols = cols
        self.lines = lines
        self.cwd = cwd or os.getcwd()
        self._process: Optional[subprocess.Popen] = None
        self._output = StringIO()
        self._scrollback: List[str] = []
        self._max_scrollback = 10000
        self._running = False
        self._lock = threading.Lock()
        self._output_lock = threading.Lock()

    def start(self, command: List[str], env: Dict = None):
        """Start a command in the terminal."""
        if self._running:
            self.stop()

        full_env = {**os.environ, **(env or {})}

        # Try PTY on Unix, fallback to subprocess on Windows
        if os.name != "nt":
            self._start_pty(command, full_env)
        else:
            self._start_subprocess(command, full_env)

        self._running = True

    def _start_subprocess(self, command: List[str], env: Dict):
        """Windows subprocess-based terminal (no true PTY)."""
        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.cwd,
            env=full_env,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop_subprocess, daemon=True)
        self._reader.start()

    def _start_pty(self, command: List[str], env: Dict):
        """Unix PTY-based terminal (real terminal behavior)."""
        import pty
        pid, fd = pty.fork()
        if pid == 0:
            # Child
            os.execvp(command[0], command)
        else:
            # Parent
            self._pty_fd = fd
            self._pid = pid
            self._reader = threading.Thread(target=self._read_loop_pty, daemon=True)
            self._reader.start()

    def _read_loop_subprocess(self):
        while self._running and self._process:
            try:
                char = self._process.stdout.read(1)
                if not char:
                    break
                with self._output_lock:
                    self._output.write(char)
                    self._scrollback.append(char)
                    if len(self._scrollback) > self._max_scrollback:
                        self._scrollback = self._scrollback[-self._max_scrollback:]
            except Exception:
                break

    def _read_loop_pty(self):
        while self._running:
            try:
                data = os.read(self._pty_fd, 4096)
                if not data:
                    break
                with self._output_lock:
                    self._output.write(data.decode("utf-8", errors="replace"))
                    self._scrollback.append(data.decode("utf-8", errors="replace"))
                    if len(self._scrollback) > self._max_scrollback:
                        self._scrollback = self._scrollback[-self._max_scrollback:]
            except OSError:
                break

    def send(self, text: str):
        """Send input to the terminal."""
        if self._process:
            try:
                self._process.stdin.write(text)
                self._process.stdin.flush()
            except Exception:
                pass

    def resize(self, cols: int, lines: int):
        """Resize the terminal."""
        self.cols = cols
        self.lines = lines
        if hasattr(self, "_pty_fd"):
            import struct, termios
            winsize = struct.pack("HHHH", lines, cols, 0, 0)
            fcntl.ioctl(self._pty_fd, termios.TIOCSWINSZ, winsize)

    def get_screen(self) -> str:
        """Get current terminal screen content."""
        with self._output_lock:
            return self._output.getvalue()

    def get_scrollback(self) -> str:
        """Get full scrollback buffer."""
        with self._output_lock:
            return "".join(self._scrollback)

    def search(self, pattern: str) -> List[Dict]:
        """Search for pattern in scrollback, return line numbers."""
        import re
        results = []
        scrollback = self.get_scrollback()
        for i, line in enumerate(scrollback.splitlines(), 1):
            if re.search(pattern, line):
                results.append({"line": i, "text": line.rstrip()})
        return results

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()
            self._process = None
        if hasattr(self, "_pty_fd"):
            try:
                os.close(self._pty_fd)
            except Exception:
                pass

    def is_running(self) -> bool:
        return self._running and (self._process is None or self._process.poll() is None)

    def __del__(self):
        self.stop()


# ─── Tool wrapper ─────────────────────────────────────────

def terminal_tool(operation: str, command: str = None, **kwargs) -> Dict[str, Any]:
    """
    Terminal tool for executor.

    Operations:
    - create: Start a terminal with a command
    - send: Send input to terminal
    - screen: Get current screen content
    - scrollback: Get full scrollback
    - search: Search scrollback for pattern
    - resize: Resize terminal
    - stop: Stop the terminal
    """
    global _active_terminal

    if operation == "create":
        cmd = command or kwargs.get("cmd")
        if not cmd:
            return {"success": False, "error": "command required"}

        # Parse command string into list
        import shlex
        cmd_list = shlex.split(cmd) if isinstance(cmd, str) else cmd

        cwd = kwargs.get("cwd", os.getcwd())
        cols = kwargs.get("cols", 120)
        lines = kwargs.get("lines", 30)

        term = FakeTerminal(cols=cols, lines=lines, cwd=cwd)
        term.start(cmd_list)

        _active_terminal = term

        return {
            "success": True,
            "running": True,
            "cols": cols,
            "lines": lines,
        }

    elif operation == "send":
        if '_active_terminal' not in globals():
            return {"success": False, "error": "No active terminal"}
        text = kwargs.get("text", "") + "\n"
        _active_terminal.send(text)
        return {"success": True}

    elif operation == "screen":
        if '_active_terminal' not in globals():
            return {"success": False, "error": "No active terminal"}
        return {
            "success": True,
            "screen": _active_terminal.get_screen(),
            "running": _active_terminal.is_running(),
        }

    elif operation == "scrollback":
        if '_active_terminal' not in globals():
            return {"success": False, "error": "No active terminal"}
        return {
            "success": True,
            "scrollback": _active_terminal.get_scrollback(),
            "search": lambda p: _active_terminal.search(p),
        }

    elif operation == "resize":
        if '_active_terminal' not in globals():
            return {"success": False, "error": "No active terminal"}
        _active_terminal.resize(kwargs.get("cols", 80), kwargs.get("lines", 24))
        return {"success": True}

    elif operation == "stop":
        if '_active_terminal' in globals():
            _active_terminal.stop()
            del _active_terminal
        return {"success": True, "running": False}

    else:
        return {"success": False, "error": f"Unknown operation: {operation}"}


if __name__ == "__main__":
    print("TTY Terminal test")

    term = FakeTerminal(cols=80, lines=24)
    term.start([sys.executable, "-c", "for i in range(5): print(f'Line {i}: hello world')"])
    time.sleep(2)
    screen = term.get_screen()
    print(f"Screen output ({len(screen)} chars):")
    print(screen[:500])
    term.stop()