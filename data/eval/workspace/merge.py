import os

# Read both files
with open('data/eval/fixtures/a.txt', 'r') as f:
    a = f.read().rstrip('\n')
with open('data/eval/fixtures/b.txt', 'r') as f:
    b = f.read().rstrip('\n')

# Ensure parent directory exists
os.makedirs('data/eval/workspace', exist_ok=True)

# Concatenate with a newline between
merged = a + '\n' + b

# Write to temp file, then rename for atomicity
tmp = 'data/eval/workspace/E05_merged.txt.tmp'
with open(tmp, 'w') as f:
    f.write(merged)
os.replace(tmp, 'data/eval/workspace/E05_merged.txt')
print('Done')
