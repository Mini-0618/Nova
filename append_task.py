import os

file_path = "data/eval/workspace/E10_append.txt"

# Ensure parent directory exists
os.makedirs(os.path.dirname(file_path), exist_ok=True)

# Append the line (create if not exists)
mode = 'a' if os.path.exists(file_path) else 'w'
with open(file_path, mode) as f:
    f.write('NEW LINE\n')

# Verify
with open(file_path, 'r') as f:
    content = f.read()
print(f"File content after append:\n---\n{content}---")
print(f"File exists: {os.path.exists(file_path)}")
