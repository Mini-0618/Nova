import sys

for line in sys.stdin:
    if 'FIXED' in line:
        print(line, end='')
