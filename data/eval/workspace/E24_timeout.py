import subprocess
import sys

def run_with_timeout(command, timeout=2):
    try:
        proc = subprocess.Popen(command, shell=True)
        proc.wait(timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print('TIMEOUT')
        return None

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = ' '.join(sys.argv[1:])
    else:
        cmd = 'python -c "import time; time.sleep(10)"'
    run_with_timeout(cmd)
