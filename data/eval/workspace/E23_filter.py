import sys

for line in sys.stdin:
    if 'ERROR' in line:
        print(line, end='')
