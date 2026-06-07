"""Test 9: Debugger basic"""
import sys
sys.path.insert(0, r'D:\codex-local')

from tools.debugger import CodeDebugger

def test_debugger_basic():
    dbg = CodeDebugger()

    # Test error case
    result = dbg.run("""
x = 10
y = 0
z = x / y
""")
    assert result.success == False, f"expected failure, got success={result.success}"
    assert result.exception_type is not None, f"exception_type={result.exception_type}"
    assert "division" in result.exception_message.lower() or "zero" in result.exception_message.lower(), \
        f"exception_message={result.exception_message}"

    # Test success case
    result2 = dbg.run('print("ok")')
    assert result2.success == True, f"expected success, got success={result2.success}"

    print("PASS: debugger basic")

if __name__ == "__main__":
    test_debugger_basic()