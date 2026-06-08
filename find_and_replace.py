#!/usr/bin/env python
"""Find all files containing 'ERROR' and replace with 'FIXED' in-place."""

import os
import sys

root = os.path.join(os.path.dirname(__file__), 'data', 'eval', 'workspace')
print(f"Searching in: {root}")

if not os.path.isdir(root):
    print(f"ERROR: Directory not found: {root}")
    sys.exit(1)

files_found = []
files_modified = []

for dirpath, dirnames, filenames in os.walk(root):
    # Skip __pycache__ directories
    dirnames[:] = [d for d in dirnames if d != '__pycache__']
    
    for filename in filenames:
        filepath = os.path.join(dirpath, filename)
        
        # Skip .pyc files
        if filename.endswith('.pyc'):
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if 'ERROR' in content:
                files_found.append(filepath)
                new_content = content.replace('ERROR', 'FIXED')
                
                # Write to temp file first, then rename (atomic write)
                temp_path = filepath + '.tmp'
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                os.rename(temp_path, filepath)
                
                files_modified.append(filepath)
                print(f"  Modified: {filepath}")
                
        except Exception as e:
            print(f"  Error reading {filepath}: {e}")

print(f"\nSummary:")
print(f"  Files containing 'ERROR': {len(files_found)}")
print(f"  Files modified: {len(files_modified)}")

if not files_found:
    print("  No files contained the word 'ERROR'.")
