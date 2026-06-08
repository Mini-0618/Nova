import json, os, tempfile

def save_users(users, path):
    # Write to temp file first, then rename atomically to prevent partial writes
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path) or '.')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(users, f)
        os.replace(tmp_path, path)
    except:
        os.unlink(tmp_path)
        raise

if __name__ == '__main__':
    users = [{'name': 'alice'}, {'name': 'bob'}]
    path = 'data/eval/workspace/E20_users.json'
    save_users(users, path)
    with open(path) as f:
        loaded = json.load(f)
    assert len(loaded) == 2, f'Expected 2 users, got {len(loaded)}'
    print('PASS')