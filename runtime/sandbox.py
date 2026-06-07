"""
Codex-Local Sandbox Engine
Provides isolated code execution environments for Python, JavaScript, Shell
Each execution runs in a separate subprocess with resource limits
Supports DebugRun with stack traces, DebugPytest, and DebugExplain
"""

import os
import sys
import uuid
import asyncio
import subprocess
import tempfile
import shutil
import time
import json
import traceback
import ast
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import threading

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


SANDBOX_DIR = Path(os.environ.get("CODEX_SANDBOX_ROOT", "D:/codex-local/sandbox"))
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ExecutionResult:
    id: str
    language: str
    code: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool
    error: Optional[str] = None
    memory_exceeded: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "language": self.language,
            "code": self.code[:500],  # truncate for storage
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "error": self.error,
            "memory_exceeded": self.memory_exceeded,
        }


@dataclass
class DebugResult:
    """Extended result for debug execution with stack trace and frames."""
    success: bool
    output: str
    error: Optional[str]
    exit_code: int
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    stack_trace: Optional[str] = None
    frames: Optional[List[Dict]] = None
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "stack_trace": self.stack_trace,
            "frames": self.frames or [],
            "duration_ms": self.duration_ms,
        }


class Sandbox:
    """
    Manages isolated code execution environments.
    Each execution gets its own temp directory.
    """

    def __init__(self, timeout_sec: int = 30, max_output_bytes: int = 512_000,
                 max_session_size_bytes: int = 100_000_000, max_file_size_bytes: int = 10_000_000,
                 max_code_size_bytes: int = 1_000_000, max_memory_mb: int = 256):
        self.timeout_sec = timeout_sec
        self.max_output_bytes = max_output_bytes
        self.max_session_size_bytes = max_session_size_bytes
        self.max_file_size_bytes = max_file_size_bytes
        self.max_code_size_bytes = max_code_size_bytes
        self.max_memory_mb = max_memory_mb
        self.executor = ThreadPoolExecutor(max_workers=8)
        self._sessions: Dict[str, Path] = {}
        self._lock = threading.Lock()

    def _create_session_dir(self, session_id: str) -> Path:
        session_dir = SANDBOX_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _check_session_size(self, session_dir: Path) -> None:
        """Check total size of session directory and raise if it exceeds max_session_size_bytes."""
        total = 0
        for entry in session_dir.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    continue
                if total > self.max_session_size_bytes:
                    raise RuntimeError(
                        f"Session directory size ({total} bytes) exceeds maximum allowed "
                        f"({self.max_session_size_bytes} bytes)"
                    )

    def _check_session_file_sizes(self, session_dir: Path) -> None:
        """Check each file in session directory against max_file_size_bytes."""
        for entry in session_dir.rglob("*"):
            if entry.is_file():
                self._check_file_size(entry)

    def _check_code_size(self, code: str) -> None:
        """Reject code that exceeds max_code_size_bytes to prevent oversized submissions."""
        size = len(code.encode("utf-8"))
        if size > self.max_code_size_bytes:
            raise RuntimeError(
                f"Code size ({size} bytes) exceeds maximum allowed "
                f"({self.max_code_size_bytes} bytes)"
            )

    def _check_file_size(self, file_path: Path) -> None:
        """Reject individual files that exceed max_file_size_bytes."""
        try:
            size = file_path.stat().st_size
            if size > self.max_file_size_bytes:
                raise RuntimeError(
                    f"File size ({size} bytes) exceeds maximum allowed "
                    f"({self.max_file_size_bytes} bytes): {file_path.name}"
                )
        except OSError:
            pass

    def _write_code(self, session_dir: Path, code: str, language: str) -> Path:
        # Enforce max code size before writing
        self._check_code_size(code)
        ext = {"python": "py", "javascript": "js", "shell": "sh", "bash": "sh"}.get(language, "txt")
        code_file = session_dir / f"main.{ext}"
        code_file.write_text(code, encoding="utf-8")
        return code_file

    def _apply_memory_limit(self, env: dict) -> dict:
        """Apply memory limit via environment variables for subprocess."""
        env = env.copy()
        if self.max_memory_mb > 0:
            env["CODEX_MEMORY_LIMIT_MB"] = str(self.max_memory_mb)
            # Python-specific memory limit via resource module (Unix) or environment
            env["PYTHONMEMORYLIMIT"] = str(self.max_memory_mb)
        return env

    def _check_memory_exceeded(self, proc: subprocess.CompletedProcess) -> bool:
        """Check if the subprocess was killed due to memory limit (OOM)."""
        if proc.returncode == -9 or proc.returncode == -6:  # SIGKILL or SIGABRT (OOM)
            return True
        # Check stderr for OOM-related messages
        stderr_text = proc.stderr.decode("utf-8", errors="replace").lower() if proc.stderr else ""
        oom_keywords = ["memory", "out of memory", "oom", "cannot allocate", "memoryerror",
                        "memory error", "killed", "allocation failure", "exit code -9"]
        if any(kw in stderr_text for kw in oom_keywords):
            return True
        return False

    def _run_python(self, code_file: Path, session_dir: Path, timeout: int) -> tuple:
        start = time.perf_counter()
        try:
            env = self._apply_memory_limit({**os.environ, "PYTHONPATH": str(session_dir)})
            proc = subprocess.run(
                [sys.executable, str(code_file)],
                capture_output=True,
                timeout=timeout,
                cwd=str(session_dir),
                env=env,
            )
            duration = int((time.perf_counter() - start) * 1000)
            memory_exceeded = self._check_memory_exceeded(proc)
            return proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace"), proc.returncode, duration, False, None, memory_exceeded
        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            return "", f"Execution timed out after {timeout} seconds", -1, duration, True, "timeout", False
        except Exception as e:
            duration = int((time.perf_counter() - start) * 1000)
            return "", str(e), -1, duration, False, str(e), False

    def _run_javascript(self, code_file: Path, session_dir: Path, timeout: int) -> tuple:
        start = time.perf_counter()
        # Try node first, then deno
        node_path = shutil.which("node") or shutil.which("node.exe") or "node"
        try:
            env = self._apply_memory_limit(os.environ)
            proc = subprocess.run(
                [node_path, str(code_file)],
                capture_output=True,
                timeout=timeout,
                cwd=str(session_dir),
                env=env,
            )
            duration = int((time.perf_counter() - start) * 1000)
            memory_exceeded = self._check_memory_exceeded(proc)
            return proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace"), proc.returncode, duration, False, None, memory_exceeded
        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            return "", f"Execution timed out after {timeout} seconds", -1, duration, True, "timeout", False
        except Exception as e:
            duration = int((time.perf_counter() - start) * 1000)
            return "", str(e), -1, duration, False, str(e), False

    def _run_shell(self, code_file: Path, session_dir: Path, timeout: int) -> tuple:
        start = time.perf_counter()
        shell = os.environ.get("CODEX_SHELL", "bash")
        shell_path = shutil.which(shell) or shutil.which("bash") or shutil.which("cmd.exe") or "bash"
        try:
            env = self._apply_memory_limit(os.environ)
            if shell.endswith("cmd.exe") or shell == "cmd":
                proc = subprocess.run(
                    [shell_path, "/c", str(code_file)],
                    capture_output=True,
                    timeout=timeout,
                    cwd=str(session_dir),
                    shell=False,
                    env=env,
                )
            else:
                # Read script content and pass via stdin to avoid path issues (WSL/MSYS2)
                script_content = code_file.read_bytes()
                proc = subprocess.run(
                    [shell_path],
                    input=script_content,
                    capture_output=True,
                    timeout=timeout,
                    cwd=str(session_dir),
                    env=env,
                )
            duration = int((time.perf_counter() - start) * 1000)
            memory_exceeded = self._check_memory_exceeded(proc)
            return proc.stdout.decode("utf-8", errors="replace"), proc.stderr.decode("utf-8", errors="replace"), proc.returncode, duration, False, None, memory_exceeded
        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            return "", f"Execution timed out after {timeout} seconds", -1, duration, True, "timeout", False
        except Exception as e:
            duration = int((time.perf_counter() - start) * 1000)
            return "", str(e), -1, duration, False, str(e), False

    def execute(self, code: str, language: str, session_id: Optional[str] = None) -> ExecutionResult:
        """
        Execute code in an isolated sandbox.
        Returns ExecutionResult with stdout, stderr, exit_code, duration.
        """
        exec_id = session_id or ("exec_" + uuid.uuid4().hex[:8])
        session_dir = self._create_session_dir(exec_id)

        # Enforce max code size before writing (caught here to return ExecutionResult)
        try:
            code_file = self._write_code(session_dir, code, language)
        except RuntimeError as e:
            return ExecutionResult(
                id=exec_id,
                language=language,
                code=code,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=0,
                timed_out=False,
                error=str(e),
            )

        # Enforce max individual file size before execution
        try:
            self._check_session_file_sizes(session_dir)
        except RuntimeError as e:
            return ExecutionResult(
                id=exec_id,
                language=language,
                code=code,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=0,
                timed_out=False,
                error=str(e),
            )

        # Enforce max session file size before execution
        try:
            self._check_session_size(session_dir)
        except RuntimeError as e:
            return ExecutionResult(
                id=exec_id,
                language=language,
                code=code,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=0,
                timed_out=False,
                error=str(e),
            )

        runners = {
            "python": self._run_python,
            "javascript": self._run_javascript,
            "shell": self._run_shell,
            "bash": self._run_shell,
        }

        runner = runners.get(language.lower())
        if not runner:
            return ExecutionResult(
                id=exec_id,
                language=language,
                code=code,
                stdout="",
                stderr=f"Unsupported language: {language}",
                exit_code=-1,
                duration_ms=0,
                timed_out=False,
                error=f"Unsupported language: {language}",
            )

        stdout, stderr, exit_code, duration_ms, timed_out, error, memory_exceeded = runner(
            code_file, session_dir, self.timeout_sec
        )

        # Post-execution: check for oversized files created during execution
        if not timed_out:
            try:
                self._check_session_file_sizes(session_dir)
                self._check_session_size(session_dir)
            except RuntimeError as e:
                stdout = ""
                stderr = str(e)
                exit_code = -1
                error = str(e)

        # If memory was exceeded, flag it in the result
        if memory_exceeded and not error:
            error = f"Memory limit exceeded (max {self.max_memory_mb} MB)"
            if not stderr:
                stderr = error

        # Truncate output to prevent memory issues
        if len(stdout) > self.max_output_bytes:
            stdout = stdout[:self.max_output_bytes] + f"\n... [truncated, {len(stdout)} bytes total]"
        if len(stderr) > self.max_output_bytes:
            stderr = stderr[:self.max_output_bytes] + f"\n... [truncated, {len(stderr)} bytes total]"

        return ExecutionResult(
            id=exec_id,
            language=language,
            code=code,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            error=error,
            memory_exceeded=memory_exceeded,
        )

    def execute_async(self, code: str, language: str, session_id: Optional[str] = None) -> asyncio.Task:
        """Submit execution to thread pool as async task."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.executor, self.execute, code, language, session_id)

    def cleanup_session(self, session_id: str):
        """Remove a session's temp directory."""
        with self._lock:
            session_dir = SANDBOX_DIR / session_id
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            self._sessions.pop(session_id, None)

    def cleanup_all(self):
        """Remove all sandbox sessions."""
        for session_id in list(self._sessions.keys()):
            self.cleanup_session(session_id)

    def list_sessions(self) -> List[str]:
        return [d.name for d in SANDBOX_DIR.iterdir() if d.is_dir()]

    def debug_run(self, code: str, session_id: Optional[str] = None, timeout: Optional[int] = None) -> DebugResult:
        """
        Execute code with full debug information: stack trace, frames with locals.
        Returns DebugResult with detailed error information.
        """
        exec_id = session_id or ("debug_" + uuid.uuid4().hex[:8])
        session_dir = self._create_session_dir(exec_id)
        timeout = timeout or self.timeout_sec

        # Create wrapper code that captures detailed exception info
        wrapper_code = f'''
import sys
import traceback
import json

try:
{self._indent_code(code, 4)}
except Exception as __exc__:
    __exc_type__ = type(__exc__).__name__
    __exc_msg__ = str(__exc__)
    __tb_str__ = traceback.format_exc()

    # Extract frames from exception traceback
    __frames__ = []
    __tb__ = __exc__.__traceback__
    while __tb__ is not None:
        __frame_info__ = __tb__.tb_frame
        __local_vars__ = {{}}
        # Snapshot keys to avoid RuntimeError from dict changing during iteration
        __keys__ = list(__frame_info__.f_locals.keys())
        for __key__ in __keys__:
            if __key__.startswith("__"):
                continue
            try:
                __val__ = __frame_info__.f_locals[__key__]
                json.dumps(__val__)
                __local_vars__[__key__] = __val__
            except (TypeError, ValueError, KeyError):
                try:
                    __local_vars__[__key__] = str(__frame_info__.f_locals.get(__key__, ""))[:200]
                except Exception:
                    __local_vars__[__key__] = "<unreadable>"

        __frames__.append({{
            "file": __frame_info__.f_code.co_filename,
            "line": __tb__.tb_lineno,
            "function": __frame_info__.f_code.co_name,
            "locals": __local_vars__
        }})
        __tb__ = __tb__.tb_next

    __result__ = {{
        "success": False,
        "output": "",
        "error": __exc_msg__,
        "exit_code": 1,
        "exception_type": __exc_type__,
        "exception_message": __exc_msg__,
        "stack_trace": __tb_str__,
        "frames": __frames__
    }}
    print("__DEBUG_RESULT__" + json.dumps(__result__))
    sys.exit(1)

# If no exception
__result__ = {{
    "success": True,
    "output": "",
    "error": None,
    "exit_code": 0,
    "exception_type": None,
    "exception_message": None,
    "stack_trace": None,
    "frames": []
}}
print("__DEBUG_RESULT__" + json.dumps(__result__))
'''

        code_file = session_dir / "debug_main.py"
        code_file.write_text(wrapper_code, encoding="utf-8")

        start = time.perf_counter()
        try:
            env = self._apply_memory_limit({**os.environ, "PYTHONPATH": str(session_dir)})
            proc = subprocess.run(
                [sys.executable, str(code_file)],
                capture_output=True,
                timeout=timeout,
                cwd=str(session_dir),
                env=env,
            )
            duration = int((time.perf_counter() - start) * 1000)
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")

            # Parse debug result from stdout
            debug_result = self._parse_debug_output(stdout, stderr, proc.returncode, duration)
            return debug_result

        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            return DebugResult(
                success=False,
                output="",
                error=f"Execution timed out after {timeout} seconds",
                exit_code=-1,
                exception_type="TimeoutError",
                exception_message=f"Execution timed out after {timeout} seconds",
                stack_trace=None,
                frames=[],
                duration_ms=duration,
            )
        except Exception as e:
            duration = int((time.perf_counter() - start) * 1000)
            return DebugResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                exception_type=type(e).__name__,
                exception_message=str(e),
                stack_trace=traceback.format_exc(),
                frames=[],
                duration_ms=duration,
            )

    def _indent_code(self, code: str, spaces: int) -> str:
        """Indent code by specified spaces."""
        indent = " " * spaces
        return "\n".join(indent + line for line in code.split("\n"))

    def _parse_debug_output(self, stdout: str, stderr: str, exit_code: int, duration: int) -> DebugResult:
        """Parse debug output to extract DebugResult."""
        # Look for __DEBUG_RESULT__ marker
        for line in stdout.split("\n"):
            if line.startswith("__DEBUG_RESULT__"):
                try:
                    data = json.loads(line[len("__DEBUG_RESULT__"):])
                    data["duration_ms"] = duration
                    # Capture any non-debug stdout as output
                    actual_stdout = "\n".join(
                        l for l in stdout.split("\n") if not l.startswith("__DEBUG_RESULT__")
                    ).strip()
                    data["output"] = actual_stdout
                    return DebugResult(**data)
                except (json.JSONDecodeError, KeyError) as e:
                    pass

        # If no debug marker found, create basic result
        return DebugResult(
            success=exit_code == 0,
            output=stdout,
            error=stderr if exit_code != 0 else None,
            exit_code=exit_code,
            exception_type="UnknownError" if exit_code != 0 else None,
            exception_message=stderr if exit_code != 0 else None,
            stack_trace=stderr if exit_code != 0 else None,
            frames=[],
            duration_ms=duration,
        )

    def debug_pytest(self, path: str, test_name: Optional[str] = None,
                     timeout: Optional[int] = None) -> DebugResult:
        """
        Run pytest on a file or directory with optional test name filter.
        Returns DebugResult with test output and failure details.
        """
        timeout = timeout or self.timeout_sec * 2  # pytest needs more time
        start = time.perf_counter()

        cmd = [sys.executable, "-m", "pytest", path, "-v", "--tb=short"]
        if test_name:
            cmd.extend(["-k", test_name])

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                cwd=str(Path(path).parent),
            )
            duration = int((time.perf_counter() - start) * 1000)
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")

            success = proc.returncode == 0
            error = None
            exception_type = None
            exception_message = None
            stack_trace = None

            if not success:
                # Parse pytest output for failure details
                lines = stdout.split("\n")
                failure_lines = []
                in_failure = False
                for line in lines:
                    if "FAILED" in line or "ERROR" in line:
                        in_failure = True
                    if in_failure:
                        failure_lines.append(line)
                        if line.strip() == "" and failure_lines:
                            break

                error = "\n".join(failure_lines) if failure_lines else "Test failed"
                exception_type = "TestFailure"
                exception_message = error
                stack_trace = stderr

            return DebugResult(
                success=success,
                output=stdout,
                error=error,
                exit_code=proc.returncode,
                exception_type=exception_type,
                exception_message=exception_message,
                stack_trace=stack_trace,
                frames=[],
                duration_ms=duration,
            )

        except subprocess.TimeoutExpired:
            duration = int((time.perf_counter() - start) * 1000)
            return DebugResult(
                success=False,
                output="",
                error=f"Pytest timed out after {timeout} seconds",
                exit_code=-1,
                exception_type="TimeoutError",
                exception_message=f"Pytest timed out after {timeout} seconds",
                stack_trace=None,
                frames=[],
                duration_ms=duration,
            )
        except Exception as e:
            duration = int((time.perf_counter() - start) * 1000)
            return DebugResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
                exception_type=type(e).__name__,
                exception_message=str(e),
                stack_trace=traceback.format_exc(),
                frames=[],
                duration_ms=duration,
            )


# ─── Global singleton ────────────────────────────────────────────────────────

_sandbox: Optional[Sandbox] = None


def get_sandbox() -> Sandbox:
    global _sandbox
    if _sandbox is None:
        _sandbox = Sandbox()
    return _sandbox


def execute_code(code: str, language: str, session_id: Optional[str] = None) -> ExecutionResult:
    return get_sandbox().execute(code, language, session_id)


def debug_run(code: str, session_id: Optional[str] = None, timeout: Optional[int] = None) -> DebugResult:
    return get_sandbox().debug_run(code, session_id, timeout)


def debug_pytest(path: str, test_name: Optional[str] = None, timeout: Optional[int] = None) -> DebugResult:
    return get_sandbox().debug_pytest(path, test_name, timeout)


def debug_explain(error_output: str, stack_trace: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze error output and provide explanation.
    Returns dict with error analysis.
    """
    analysis = {
        "error_type": "Unknown",
        "description": "",
        "suggestion": "",
        "location": None,
    }

    # Parse common Python errors
    error_patterns = {
        "SyntaxError": ("Syntax error in code", "Check the syntax near the error location"),
        "IndentationError": ("Indentation error", "Check indentation levels, use consistent spaces/tabs"),
        "NameError": ("Name not defined", "Check if the variable/function is defined before use"),
        "TypeError": ("Type mismatch", "Check argument types and function signatures"),
        "ValueError": ("Invalid value", "Check input values and their constraints"),
        "AttributeError": ("Attribute not found", "Check if the object has the requested attribute"),
        "KeyError": ("Key not found", "Check if the key exists in the dictionary"),
        "IndexError": ("Index out of range", "Check list/string length before accessing by index"),
        "ZeroDivisionError": ("Division by zero", "Add a check for zero before division"),
        "FileNotFoundError": ("File not found", "Check file path and permissions"),
        "ImportError": ("Import failed", "Check if the module is installed and spelled correctly"),
        "ModuleNotFoundError": ("Module not found", "Install the module with pip or check the name"),
        "RuntimeError": ("Runtime error", "Check the error message for details"),
        "MemoryError": ("Out of memory", "Reduce data size or optimize memory usage"),
        "RecursionError": ("Recursion limit exceeded", "Add a base case or increase recursion limit"),
    }

    # Try to extract error type from output
    for error_type, (desc, suggestion) in error_patterns.items():
        if error_type in error_output:
            analysis["error_type"] = error_type
            analysis["description"] = desc
            analysis["suggestion"] = suggestion
            break

    # Try to extract line number
    import re
    line_match = re.search(r'line (\d+)', error_output)
    if line_match:
        analysis["location"] = {"line": int(line_match.group(1))}

    # Extract file path if present
    file_match = re.search(r'File "([^"]+)"', error_output)
    if file_match:
        if analysis["location"] is None:
            analysis["location"] = {}
        analysis["location"]["file"] = file_match.group(1)

    return analysis


if __name__ == "__main__":
    # Quick test
    sb = Sandbox()

    # Test basic execution
    result = sb.execute('print("hello from sandbox")', "python")
    print(f"Exit: {result.exit_code}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")
    print(f"Duration: {result.duration_ms}ms")

    # Test debug run
    debug_result = sb.debug_run('x = 1/0')
    print(f"\nDebug Run:")
    print(f"Success: {debug_result.success}")
    print(f"Exception: {debug_result.exception_type}")
    print(f"Message: {debug_result.exception_message}")
    print(f"Frames: {len(debug_result.frames)}")

    print(f"\nSessions: {sb.list_sessions()}")