"""Test 8: Refactorer basic rename"""
import sys
sys.path.insert(0, r'D:\codex-local')

from tools.refactorer import MultiModuleRefactorer
import tempfile
import os

def test_refactorer_basic():
    tmp = tempfile.mkdtemp()

    # Create a file with a function to rename
    with open(os.path.join(tmp, "example.py"), "w") as f:
        f.write("""def old_function_name():
    return 42

result = old_function_name()
print(old_function_name())
""")

    ref = MultiModuleRefactorer(tmp)
    plan = ref.rename_symbol("old_function_name", "new_function_name",
                              files=[os.path.join(tmp, "example.py")])

    assert len(plan.changes) == 1, f"changes={len(plan.changes)}"
    assert "new_function_name" in plan.changes[0].new_content

    # Apply
    results = ref.apply_plan(plan)
    assert len(results["failed"]) == 0, f"failed={results['failed']}"

    # Verify file content
    with open(os.path.join(tmp, "example.py")) as f:
        content = f.read()
    assert "new_function_name" in content
    assert "old_function_name" not in content

    import shutil
    shutil.rmtree(tmp)
    print("PASS: refactorer basic")

if __name__ == "__main__":
    test_refactorer_basic()