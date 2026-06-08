import subprocess
import sys

def run_with_timeout(command, timeout=2):
    """Run a command with a timeout. Print 'TIMEOUT' if it exceeds."""
    try:
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            print(stdout, end='')
            if stderr:
                print(stderr, end='', file=sys.stderr)
            return proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            print('TIMEOUT')
            return -1
    except Exception as e:
        print(f'Error: {e}')
        return -1

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = ' '.join(sys.argv[1:])
    else:
        cmd = sys.stdin.read().strip()
    sys.exit(run_with_timeout(cmd))
