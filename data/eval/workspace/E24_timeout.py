import subprocess
import sys

def run_with_timeout(command, timeout=2):
    """Run a command with a timeout. Print 'TIMEOUT' if it exceeds."""
    proc = None
    try:
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait(timeout=timeout)
        stdout, stderr = proc.communicate()
        if stdout:
            print(stdout.decode(), end='')
        if stderr:
            print(stderr.decode(), end='', file=sys.stderr)
        return proc.returncode
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
            proc.wait()
        print('TIMEOUT')
        return -1

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = ' '.join(sys.argv[1:])
    else:
        cmd = 'python -c "import time; time.sleep(10)"'
    run_with_timeout(cmd)
