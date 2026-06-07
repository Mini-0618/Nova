"""Test 4: Edit file (old_string -> new_string)"""
import sys
sys.path.insert(0, r'D:\codex-local')

from tools.executor import get_executor
import tempfile

def test_edit_file():
    ex = get_executor()
    tmp = tempfile.mktemp(suffix=".py")

    # Write initial
    ex.write(tmp, "def foo():\n    return 42\n")

    # Edit
    r = ex.edit(tmp, "return 42", "return 100")
    assert r["success"] == True, f"edit failed: {r}"

    # Verify
    r = ex.read(tmp)
    assert "return 100" in r["content"], f"content={r['content']!r}"

    import os
    os.unlink(tmp)
    print("PASS: edit file")

if __name__ == "__main__":
    test_edit_file()