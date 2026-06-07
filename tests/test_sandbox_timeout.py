"""Test 2: Sandbox timeout"""
import sys
sys.path.insert(0, r'D:\codex-local')

from runtime.sandbox import Sandbox

def test_sandbox_timeout():
    sb = Sandbox(timeout_sec=2)
    # Infinite loop
    result = sb.execute('while True: pass', "python")
    assert result.timed_out == True, f"expected timeout, got timed_out={result.timed_out}"
    assert result.exit_code == -1, f"exit_code={result.exit_code}"
    print("PASS: sandbox timeout")

if __name__ == "__main__":
    test_sandbox_timeout()