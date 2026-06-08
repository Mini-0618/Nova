#!/usr/bin/env python3
"""E23: Pipe processing - filter lines containing FIXED."""
import sys
for line in sys.stdin:
    if 'FIXED' in line:
        print(line, end='')
