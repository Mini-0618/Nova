"""Test 3: File read/write via ToolExecutor"""
import sys
sys.path.insert(0, r'D:\codex-local')

from tools.executor import get_executor
import tempfile
import os

def test_file_read_write():
    ex = get_executor()
    tmp = tempfile.mktemp(suffix=".txt")

    # Write
    r = ex.write(tmp, "hello world\nline2")
    assert r["success"] == True, f"write failed: {r}"

    # Read
    r = ex.read(tmp)
    assert r["success"] == True, f"read failed: {r}"
    assert "hello world" in r["content"], f"content={r['content']!r}"

    # Cleanup
    os.unlink(tmp)
    print("PASS: file read/write")

if __name__ == "__main__":
    test_file_read_write()