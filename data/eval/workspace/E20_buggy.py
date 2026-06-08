import json, os, tempfile

def save_users(users, path):
    # Atomic write: write to temp file, then rename
    tmp = tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(path) or '.', delete=False, suffix='.tmp')
    try:
        json.dump(users, tmp)
        tmp.close()
        os.replace(tmp.name, path)
    except:
        # Clean up temp file on failure
        try:
            os.unlink(tmp.name)
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