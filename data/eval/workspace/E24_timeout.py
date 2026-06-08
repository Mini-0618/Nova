#!/usr/bin/env python3
"""E24: Subprocess with timeout."""
import subprocess
import sys

try:
    result = subprocess.run(
        [sys.executable, '-c', 'import time; time.sleep(10)'],
        timeout=2,
        capture_output=True,
        text=True,
    )
    print('COMPLETED')
except subprocess.TimeoutExpired:
    print('TIMEOUT')
