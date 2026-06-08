import subprocess
import sys

def run_with_timeout(command, timeout=2):
    """Run a command with a timeout. Print 'TIMEOUT' if it exceeds."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print('TIMEOUT')
        return None, None, None

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1:]
    else:
        cmd = ['python', '-c', 'import time; time.sleep(10)']
    run_with_timeout(cmd)
