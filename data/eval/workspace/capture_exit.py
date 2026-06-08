import subprocess
import os

# Run the command and capture the exit code
result = subprocess.run(
    ["python", "-c", "import sys; sys.exit(42)"],
    capture_output=True,
    text=True
)

exit_code = result.returncode
print(f"Captured exit code: {exit_code}")

# Create directory if it doesn't exist
target_dir = "D:/codex-local/data/eval/workspace"
os.makedirs(target_dir, exist_ok=True)

# Write to temp file first, then rename (atomic-ish write)
tmp_path = os.path.join(target_dir, "E25_exitcode.txt.tmp")
final_path = os.path.join(target_dir, "E25_exitcode.txt")

with open(tmp_path, "w") as f:
    f.write(str(exit_code))

os.rename(tmp_path, final_path)
print(f"Written exit code {exit_code} to {final_path}")

# Verify
with open(final_path, "r") as f:
    content = f.read()
print(f"Verification: file contains '{content}'")
