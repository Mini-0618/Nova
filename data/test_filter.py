import subprocess
import sys

# Test the filter script
proc = subprocess.run(
    [sys.executable, r'D:\data\eval\workspace\E23_filter.py'],
    input='INFO ok\nERROR bad\nINFO fine\n',
    capture_output=True,
    text=True
)

expected = 'ERROR bad'
actual = proc.stdout.strip()
assert actual == expected, f"Expected '{expected}', got '{actual}'"
assert proc.returncode == 0, f"Non-zero return code: {proc.returncode}"
print("TEST PASSED: Script correctly filters lines containing 'ERROR'")
print(f"Output: {repr(proc.stdout)}")
