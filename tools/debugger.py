"""
Codex-Local Code Debugger
pdb-based debugger integration with pytest runner for detailed error reporting,
variable inspection, stack traces, breakpoints, and watch expressions.
"""

import os
import sys
import json
import traceback
import pdb
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr


# ─── Debugger Types ─────────────────────────────────────────────────────────

@dataclass
class StackFrame:
    filename: str
    lineno: int
    function: str
    code_context: str
    locals: Dict[str, str] = field(default_factory=dict)
    globals: Dict[str, str] = field(default_factory=dict)


@dataclass
class Breakpoint:
    id: int
    filename: str
    lineno: int
    condition: Optional[str] = None
    hit_count: int = 0
    enabled: bool = True


@dataclass
class WatchExpression:
    expression: str
    last_value: Optional[str] = None
    changed: bool = False


@dataclass
class DebugResult:
    success: bool
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    stack_trace: Optional[str] = None
    frames: List[StackFrame] = field(default_factory=list)
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None


# ─── Capture Debugger ────────────────────────────────────────────────────────

class CaptureDebugger(pdb.Pdb):
    """
    PDB debugger that captures output instead of interacting with stdin.
    Used for automated debugging sessions.
    """

    def __init__(self, target_locals=None, target_globals=None):
        super().__init__()
        self.target_locals = target_locals or {}
        self.target_globals = target_globals or {}
        self._output = StringIO()
        self._stack_frames: List[StackFrame] = []
        self._watch_expressions: List[WatchExpression] = []

    def setup(self, f, t):
        """Setup debugger with frame."""
        super().setup(f, t)

    def do_where(self, arg):
        """Print stack trace."""
        if not hasattr(self, 'stack') or not self.stack:
            self.stack, idx = self.get_stack(self.curframe, self.curframe.f_trace)
        self.stack_printing_manager = self
        for frame_lineno in self.stack:
            self.print_stack_entry(frame_lineno)
        return None

    def print_stack_entry(self, frame_lineno, prefix="-> "):
        """Print a stack frame entry."""
        frame, lineno = frame_lineno
        filename = self.canonic(frame.f_code.co_filename)
        funcname = frame.f_code.co_name
        try:
            content = Path(filename).read_text(encoding="utf-8", errors="replace").splitlines()[lineno - 1]
        except Exception:
            content = "(source unavailable)"
        print(f"{prefix}{filename}({lineno}) {funcname}(): {content.strip()}", file=self._output)

    def capture_stack(self):
        """Capture current stack frames."""
        if not hasattr(self, 'stack') or not self.stack:
            self.stack, idx = self.get_stack(self.curframe, self.curframe.f_trace)
        self._stack_frames = []
        for frame_lineno in self.stack:
            frame, lineno = frame_lineno
            filename = self.canonic(frame.f_code.co_filename)
            funcname = frame.f_code.co_name
            try:
                ctx = Path(filename).read_text(encoding="utf-8", errors="replace").splitlines()[lineno - 1]
            except Exception:
                ctx = ""
            # Get locals for this frame
            frame_obj = frame
            locals_dump = {}
            if hasattr(frame_obj, 'f_locals'):
                for k, v in list(frame_obj.f_locals.items())[:20]:
                    try:
                        locals_dump[k] = repr(v)[:100]
                    except Exception:
                        locals_dump[k] = "<unrepresentable>"
            self._stack_frames.append(StackFrame(
                filename=filename,
                lineno=lineno,
                function=funcname,
                code_context=ctx.strip(),
                locals=locals_dump,
            ))

    def get_output(self) -> str:
        return self._output.getvalue()


def _extract_frames_from_traceback(tb_str: str) -> List[StackFrame]:
    """Parse a traceback string into StackFrame objects."""
    frames = []
    for line in tb_str.split("\n"):
        m = re.search(r'File "([^"]+)", line (\d+), (\w+)', line)
        if m:
            filename, lineno, funcname = m.groups()
            try:
                ctx = Path(filename).read_text(encoding="utf-8", errors="replace").splitlines()[int(lineno) - 1]
            except Exception:
                ctx = ""
            frames.append(StackFrame(
                filename=filename,
                lineno=int(lineno),
                function=funcname,
                code_context=ctx.strip(),
            ))
    return frames


# ─── Code Execution with Debug ─────────────────────────────────────────────

def run_with_debugger(code: str, globals_dict: Optional[Dict] = None,
                      locals_dict: Optional[Dict] = None) -> DebugResult:
    """
    Execute code through an interactive debugger that pauses on exception.

    Returns detailed information including:
    - Full stack trace
    - Local variables at each frame
    - Exception type and message
    """
    output = StringIO()
    globals_dict = globals_dict or {}
    locals_dict = locals_dict or {}

    try:
        with redirect_stdout(output), redirect_stderr(output):
            exec(compile(code, "<debug>", "exec"), globals_dict, locals_dict)
        return DebugResult(
            success=True,
            output=output.getvalue(),
            exit_code=0,
        )
    except Exception:
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        frames = _extract_frames_from_traceback(tb_str)

        # Get detailed local variables from actual traceback
        detailed_frames = []
        tb = exc_tb
        while tb:
            frame = tb.tb_frame
            filename = frame.f_code.co_filename
            lineno = tb.tb_lineno
            funcname = frame.f_code.co_name
            try:
                ctx = Path(filename).read_text(encoding="utf-8", errors="replace").splitlines()[lineno - 1]
            except Exception:
                ctx = ""
            locals_dump = {}
            for k, v in list(frame.f_locals.items())[:30]:
                try:
                    locals_dump[k] = repr(v)[:150]
                except Exception:
                    locals_dump[k] = "<unrepresentable>"
            detailed_frames.append(StackFrame(
                filename=filename,
                lineno=lineno,
                function=funcname,
                code_context=ctx.strip(),
                locals=locals_dump,
            ))
            tb = tb.tb_next

        return DebugResult(
            success=False,
            output=output.getvalue(),
            error=str(exc_value),
            exit_code=1,
            stack_trace=tb_str,
            frames=detailed_frames,
            exception_type=exc_type.__name__,
            exception_message=str(exc_value),
        )


# ─── Pytest Integration ─────────────────────────────────────────────────────

def run_pytest(file_path: str, test_name: Optional[str] = None,
               verbose: bool = True, capture: str = "no",
               timeout: int = 60) -> DebugResult:
    """
    Run pytest on a file and return detailed results.
    Much better than simple code execution for testing.

    Args:
        file_path: Path to test file or directory
        test_name: Specific test function (e.g., "test_example")
        verbose: -v flag
        capture: 'no'|'stdout'|'no' - no capture = see print statements
        timeout: seconds before force kill
    """
    cmd = [sys.executable, "-m", "pytest", file_path]

    if verbose:
        cmd.append("-v")
    if capture == "no":
        cmd.append("-s")  # Don't capture stdout
    if test_name:
        cmd.append(f"-k={test_name}")
    cmd.append("--tb=long")  # Long traceback format
    cmd.append("--pdbcls=IPython.terminal.debugger:TerminalPdb")  # nicer debugger

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            text=True,
            cwd=str(Path(file_path).parent if Path(file_path).is_file() else file_path),
        )
        return DebugResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr if result.returncode != 0 else None,
            exit_code=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return DebugResult(
            success=False,
            error=f"Pytest timed out after {timeout}s",
            exit_code=-1,
            exception_type="TimeoutError",
        )
    except Exception as e:
        return DebugResult(
            success=False,
            error=str(e),
            exit_code=-1,
        )


def run_test_with_breakpoint(code: str, globals_dict: Optional[Dict] = None,
                              locals_dict: Optional[Dict] = None) -> DebugResult:
    """
    Run code and drop into pdb debugger if an exception occurs.
    For CI/automated use, captures the session.
    """
    dbg = CaptureDebugger(globals_dict, locals_dict)
    output = StringIO()

    try:
        with redirect_stdout(output), redirect_stderr(output):
            dbg.run(code, globals_dict or {}, locals_dict or {})
    except Exception:
        pass  # Exception info already captured

    return DebugResult(
        success=True,
        output=output.getvalue() + dbg.get_output(),
        frames=dbg._stack_frames,
    )


# ─── Variable Inspector ─────────────────────────────────────────────────────

def inspect_variable(var, max_depth: int = 3, _current_depth: int = 0) -> str:
    """
    Pretty-inspect a variable, recursively expanding dicts and objects.
    """
    if _current_depth >= max_depth:
        return repr(var)[:200]

    try:
        vtype = type(var).__name__
        if isinstance(var, dict):
            if len(var) == 0:
                return "{}"
            items = []
            for k, v in list(var.items())[:10]:
                items.append(f"{repr(k)}: {inspect_variable(v, max_depth, _current_depth + 1)}")
            prefix = "{" if _current_depth > 0 else ""
            suffix = "}" if _current_depth > 0 else ""
            return prefix + ", ".join(items) + suffix
        elif isinstance(var, (list, tuple)):
            if len(var) == 0:
                return repr(var)
            items = [inspect_variable(i, max_depth, _current_depth + 1) for i in list(var)[:20]]
            bracket = "[" if isinstance(var, list) else "("
            close = "]" if isinstance(var, list) else ")"
            return bracket + ", ".join(items) + close
        elif isinstance(var, str):
            return repr(var[:200])
        else:
            s = repr(var)
            return s[:200] if len(s) > 200 else s
    except Exception:
        return repr(var)[:100]


def inspect_frame_locals(frame) -> Dict[str, str]:
    """Get a detailed inspection of all local variables in a frame."""
    result = {}
    if hasattr(frame, 'f_locals'):
        for name, value in list(frame.f_locals.items())[:50]:
            result[name] = inspect_variable(value)
    return result


# ─── Breakpoint Manager ─────────────────────────────────────────────────────

class BreakpointManager:
    """Manage breakpoints across files."""

    def __init__(self):
        self.breakpoints: Dict[str, List[Breakpoint]] = {}  # file -> breakpoints
        self._next_id = 1

    def add(self, filename: str, lineno: int, condition: Optional[str] = None) -> Breakpoint:
        bp = Breakpoint(id=self._next_id, filename=filename, lineno=lineno, condition=condition)
        self._next_id += 1
        self.breakpoints.setdefault(filename, []).append(bp)
        return bp

    def remove(self, filename: str, lineno: int) -> bool:
        if filename in self.breakpoints:
            self.breakpoints[filename] = [bp for bp in self.breakpoints[filename] if bp.lineno != lineno]
            return True
        return False

    def list_all(self) -> List[Breakpoint]:
        all_bp = []
        for bps in self.breakpoints.values():
            all_bp.extend(bps)
        return all_bp

    def get_for_file(self, filename: str) -> List[Breakpoint]:
        return self.breakpoints.get(filename, [])

    def to_pdb_commands(self) -> List[str]:
        """Generate pdb commands to set all breakpoints."""
        cmds = []
        for filepath, bps in self.breakpoints.items():
            for bp in bps:
                cmds.append(f"break {filepath}:{bp.lineno}")
                # Append condition command if breakpoint has a condition
                if bp.condition:
                    cmds.append(f"condition {bp.id} {bp.condition}")
        return cmds


# ─── Main Debugger Interface ─────────────────────────────────────────────────

class CodeDebugger:
    """
    High-level debugger interface combining pdb, pytest, and inspection.

    Usage:
        debugger = CodeDebugger()
        result = debugger.run('print(x)', {'x': 10})
        print(result.exception_type, result.exception_message)
        for frame in result.frames:
            print(f"{frame.filename}:{frame.lineno} {frame.function}")
            print(frame.locals)
    """

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root or "D:/")
        self.bp_manager = BreakpointManager()

    def run(self, code: str, globals_dict: Optional[Dict] = None,
            locals_dict: Optional[Dict] = None, timeout: int = 30) -> DebugResult:
        """Run code and capture any exceptions with full debug info."""
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError("Execution timed out")

        try:
            # Set timeout if possible (Unix only)
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
        except (AttributeError, ValueError):
            pass  # Windows doesn't have SIGALRM

        try:
            result = run_with_debugger(code, globals_dict, locals_dict)
            return result
        except TimeoutError as e:
            return DebugResult(
                success=False,
                error=str(e),
                exit_code=-1,
                exception_type="TimeoutError",
            )
        finally:
            try:
                signal.alarm(0)
            except Exception:
                pass

    def run_file(self, file_path: str, function: Optional[str] = None) -> DebugResult:
        """Run a Python file with full debugging."""
        path = self.workspace_root / file_path if not Path(file_path).is_absolute() else Path(file_path)
        if not path.exists():
            return DebugResult(success=False, error=f"File not found: {path}")

        code = path.read_text(encoding="utf-8", errors="replace")

        # Proper globals/locals so nested functions can resolve each other
        global_scope = {
            "__name__": "__main__",
            "__file__": str(path),
            "__builtins__": __builtins__,
        }
        return self.run(code, globals_dict=global_scope, locals_dict=global_scope)

    def test(self, path: str, test_name: Optional[str] = None) -> DebugResult:
        """Run pytest on a file."""
        return run_pytest(path, test_name)

    def add_breakpoint(self, file: str, lineno: int, condition: Optional[str] = None) -> Breakpoint:
        return self.bp_manager.add(file, lineno, condition)

    def remove_breakpoint(self, file: str, lineno: int) -> bool:
        return self.bp_manager.remove(file, lineno)

    def explain_error(self, result: DebugResult) -> str:
        """Generate a human-readable explanation of a debug result."""
        if result.success:
            return "Code executed successfully without errors."

        lines = [f"### Error: {result.exception_type}"]

        if result.exception_message:
            lines.append(f"\n**Message:** `{result.exception_message}`")

        if result.stack_trace:
            lines.append("\n**Stack Trace:**\n```")
            lines.append(result.stack_trace)
            lines.append("```")

        if result.frames:
            lines.append("\n**Frames:**")
            for i, frame in enumerate(result.frames):
                lines.append(f"\n{i+1}. `{frame.filename}:{frame.lineno}` in `{frame.function}`")
                if frame.code_context:
                    lines.append(f"   > {frame.code_context}")
                if frame.locals:
                    lines.append("   **Locals:**")
                    for name, val in list(frame.locals.items())[:10]:
                        lines.append(f"   - `{name}` = {val}")

        return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dbg = CodeDebugger()
    result = dbg.run("""
x = 10
y = 0
result = x / y
""")
    print("Success:", result.success)
    print("Exception:", result.exception_type)
    print("Message:", result.exception_message)
    print(dbg.explain_error(result))