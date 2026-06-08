import sys
import os

# The exit code we want to capture
exit_code = 42

# Ensure the target directory exists
target_dir = "D:/codex-local/data/eval/workspace"
os.makedirs(target_dir, exist_ok=True)

# Write to temporary file first, then rename (atomic-ish)
tmp_path = os.path.join(target_dir, "E25_exitcode.txt.tmp")
final_path = os.path.join(target_dir, "E25_exitcode.txt")

with open(tmp_path, "w") as f:
    f.write(str(exit_code))

os.rename(tmp_path, final_path)

# Verify
with open(final_path, "r") as f:
    content = f.read()
print(f"Written '{content}' to {final_path}")
