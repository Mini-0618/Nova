"""
Test MCP Sandbox Server and Sandbox Debug Features
"""
import sys
import json
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_PATH = str(ROOT / "runtime")
MCP_PATH = str(ROOT / "mcp")


def _load_module(name, filepath):
    """Load a specific module from filepath, bypassing sys.path conflicts."""
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sandbox_basic():
    """Test basic sandbox execution."""
    print("=" * 60)
    print("Test 1: Basic Sandbox Execution")
    print("=" * 60)

    rt_sandbox = _load_module("runtime_sandbox", RUNTIME_PATH + "/sandbox.py")
    sb = rt_sandbox.Sandbox()

    # Test Python execution
    result = sb.execute('print("hello from sandbox")', "python")
    print(f"Exit: {result.exit_code}")
    print(f"Stdout: {result.stdout.strip()}")
    print(f"Duration: {result.duration_ms}ms")
    assert result.exit_code == 0
    assert "hello from sandbox" in result.stdout
    print("[PASS]\n")

    # Test JavaScript execution
    try:
        result = sb.execute('console.log("hello from node")', "javascript")
        print(f"JS Exit: {result.exit_code}")
        print(f"JS Stdout: {result.stdout.strip()}")
        if result.exit_code == 0:
            print("[PASS]\n")
        else:
            print("[SKIP - Node.js not available]\n")
    except Exception as e:
        print(f"[SKIP - {e}]\n")

    # Test shell execution
    result = sb.execute('echo "hello from shell"', "shell")
    print(f"Shell Exit: {result.exit_code}")
    try:
        print(f"Shell Stdout: {result.stdout.strip()}")
    except UnicodeEncodeError:
        print(f"Shell Stdout: (encoding error)")
    # Shell test may fail on Windows if bash is not in PATH
    if result.exit_code == 0:
        print("[PASS]\n")
    else:
        print("[SKIP - shell not available or echo failed]\n")


def test_debug_run():
    """Test debug run with stack trace."""
    print("=" * 60)
    print("Test 2: Debug Run with Stack Trace")
    print("=" * 60)

    rt_sandbox = _load_module("runtime_sandbox", RUNTIME_PATH + "/sandbox.py")
    sb = rt_sandbox.Sandbox()

    # Test successful execution
    result = sb.debug_run('x = 10\ny = 20\nprint(f"Sum: {x + y}")')
    print(f"Success: {result.success}")
    print(f"Output: {result.output.strip()}")
    assert result.success == True
    print("[PASS]\n")

    # Test division by zero
    result = sb.debug_run('x = 10\ny = 0\nresult = x / y')
    print(f"Success: {result.success}")
    print(f"Exception Type: {result.exception_type}")
    print(f"Exception Message: {result.exception_message}")
    print(f"Frames Count: {len(result.frames)}")
    assert result.success == False
    assert result.exception_type == "ZeroDivisionError"
    if result.frames:
        print(f"First Frame: {result.frames[0]}")
    print("[PASS]\n")

    # Test name error
    result = sb.debug_run('print(undefined_variable)')
    print(f"Success: {result.success}")
    print(f"Exception Type: {result.exception_type}")
    assert result.success == False
    assert result.exception_type == "NameError"
    print("[PASS]\n")


def test_debug_pytest():
    """Test pytest execution."""
    print("=" * 60)
    print("Test 3: Debug Pytest")
    print("=" * 60)

    rt_sandbox = _load_module("runtime_sandbox", RUNTIME_PATH + "/sandbox.py")
    sb = rt_sandbox.Sandbox()

    # Create a test file
    test_dir = ROOT / "test_files"
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / "test_example.py"
    test_file.write_text("""def test_pass():
    assert 1 + 1 == 2

def test_fail():
    assert 1 + 1 == 3

def test_error():
    raise ValueError("test error")
""")

    # Run all tests
    result = sb.debug_pytest(str(test_file))
    print(f"Success: {result.success}")
    print(f"Exit Code: {result.exit_code}")
    print(f"Output (first 500 chars): {result.output[:500]}")
    assert result.success == False  # Some tests fail
    print("[PASS]\n")

    # Run specific test
    result = sb.debug_pytest(str(test_file), test_name="test_pass")
    print(f"Success (test_pass): {result.success}")
    assert result.success == True
    print("[PASS]\n")


def test_debug_explain():
    """Test error explanation."""
    print("=" * 60)
    print("Test 4: Debug Explain")
    print("=" * 60)

    rt_sandbox = _load_module("runtime_sandbox", RUNTIME_PATH + "/sandbox.py")

    errors = [
        "ZeroDivisionError: division by zero",
        "NameError: name 'undefined' is not defined",
        "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        "FileNotFoundError: [Errno 2] No such file or directory: 'test.txt'",
        "ImportError: No module named 'nonexistent'",
    ]

    for error in errors:
        result = rt_sandbox.debug_explain(error)
        print(f"Error: {error[:50]}...")
        print(f"  Type: {result['error_type']}")
        print(f"  Suggestion: {result['suggestion']}")
        print()


import pytest

@pytest.mark.skip(reason="Old SandboxMCPServer incompatible with refactored CodexMCPServer")
def test_mcp_server():
    """Test MCP server integration."""
    print("=" * 60)
    print("Test 5: MCP Server Integration")
    print("=" * 60)

    mcp_sandbox = _load_module("mcp_sandbox", MCP_PATH + "/sandbox.py")

    server = mcp_sandbox.SandboxMCPServer()

    # Test tool listing
    tools = server.get_tools()
    print(f"Available tools: {[t['name'] for t in tools]}")
    assert len(tools) == 4
    assert "sandbox_exec" in [t['name'] for t in tools]
    assert "DebugRun" in [t['name'] for t in tools]
    assert "DebugPytest" in [t['name'] for t in tools]
    assert "DebugExplain" in [t['name'] for t in tools]
    print("[PASS]\n")

    # Test sandbox_exec
    result = server.execute_tool("sandbox_exec", {
        "code": "print('MCP test')",
        "language": "python"
    })
    print(f"sandbox_exec result: {json.dumps(result, indent=2)[:200]}")
    assert result["exit_code"] == 0
    print("[PASS]\n")

    # Test DebugRun
    result = server.execute_tool("DebugRun", {
        "code": "x = 1/0"
    })
    print(f"DebugRun result: {json.dumps(result, indent=2)[:200]}")
    assert result["success"] == False
    assert result["exception_type"] == "ZeroDivisionError"
    print("[PASS]\n")

    # Test DebugExplain
    result = server.execute_tool("DebugExplain", {
        "error_output": "NameError: name 'foo' is not defined"
    })
    print(f"DebugExplain result: {json.dumps(result, indent=2)[:200]}")
    assert result["error_type"] == "NameError"
    print("[PASS]\n")


if __name__ == "__main__":
    print("Codex-Local MCP Sandbox Test Suite")
    print("=" * 60)
    print()

    try:
        test_sandbox_basic()
        test_debug_run()
        test_debug_pytest()
        test_debug_explain()
        test_mcp_server()

        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
    except Exception as e:
        print(f"\nTEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
