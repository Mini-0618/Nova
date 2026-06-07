"""Test 1: Sandbox Python execution"""
import sys
sys.path.insert(0, r'D:\codex-local')

from runtime.sandbox import get_sandbox

def test_sandbox_python_exec():
    sb = get_sandbox()
    result = sb.execute('print("hello")', "python")
    assert result.exit_code == 0, f"exit_code={result.exit_code}"
    assert "hello" in result.stdout, f"stdout={result.stdout!r}"
    print("PASS: sandbox python exec")

if __name__ == "__main__":
    test_sandbox_python_exec()