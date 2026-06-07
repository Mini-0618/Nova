import json, os, tempfile

def save_users(users, path):
    dir_name = os.path.dirname(path) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(users, f)
        os.replace(tmp_path, path)  # atomic on POSIX and Windows
    except BaseException:
        # Clean up the temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

if __name__ == '__main__':
    users = [{'name': 'alice'}, {'name': 'bob'}]
    path = 'data/eval/workspace/E20_users.json'
    save_users(users, path)
    with open(path) as f:
        loaded = json.load(f)
    assert len(loaded) == 2, f'Expected 2 users, got {len(loaded)}'
    print('PASS')