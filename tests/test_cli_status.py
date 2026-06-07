"""Test 10: CLI status command"""
import sys
import subprocess

def test_cli_status():
    result = subprocess.run(
        [sys.executable, r"D:\codex-local\cli.py", "status"],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result.returncode == 0, f"returncode={result.returncode}, stderr={result.stderr}"

    import json
    data = json.loads(result.stdout)
    assert "total_sessions" in data, f"keys={list(data.keys())}"

    print("PASS: CLI status")

if __name__ == "__main__":
    test_cli_status()