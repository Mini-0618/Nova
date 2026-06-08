import subprocess
import sys

def run_with_timeout(cmd, timeout=2):
    """Run a command with a timeout. Print 'TIMEOUT' if it exceeds."""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        print(proc.stdout, end='')
        if proc.stderr:
            print(proc.stderr, end='', file=sys.stderr)
        return proc.returncode
    except subprocess.TimeoutExpired:
        print('TIMEOUT')
        return -1

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = ' '.join(sys.argv[1:])
    else:
        cmd = sys.stdin.read().strip()
    sys.exit(run_with_timeout(cmd))
