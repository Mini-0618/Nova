import subprocess, os

result = subprocess.run(["python", "--version"], capture_output=True, text=True)
version_output = result.stdout.strip() or result.stderr.strip()

output_path = os.path.join("D:", "codex-local", "data", "eval", "workspace", "E21_version.txt")
with open(output_path, "w") as f:
    f.write(version_output + "\n")

print(f"Python version: {version_output}")
print(f"Saved to: {output_path}")
