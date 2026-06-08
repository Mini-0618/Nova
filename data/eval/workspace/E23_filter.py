import sys

def filter_errors():
    for line in sys.stdin:
        if 'ERROR' in line:
            print(line, end='')

filter_errors()
