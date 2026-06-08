import subprocess
import os
import tempfile

result = subprocess.run(
    ['python', '-c', 'import sys; sys.exit(42)'],
    capture_output=True
)

exit_code = str(result.returncode)

output_dir = 'data/eval/workspace'
os.makedirs(output_dir, exist_ok=True)

# Write to temp file first, then rename for atomicity
final_path = os.path.join(output_dir, 'E25_exitcode.txt')
tmp_fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix='.tmp')
try:
    with os.fdopen(tmp_fd, 'w') as f:
        f.write(exit_code)
    os.rename(tmp_path, final_path)
except:
    os.unlink(tmp_path)
    raise

print(f"Exit code: {exit_code}")
print(f"Written to: {final_path}")
