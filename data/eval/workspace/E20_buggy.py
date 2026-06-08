import json, os, tempfile, shutil

def save_users(users, path):
    tmp = tempfile.NamedTemporaryFile('w', delete=False, dir=os.path.dirname(path))
    try:
        json.dump(users, tmp)
        tmp.close()
        shutil.move(tmp.name, path)
    except:
        tmp.close()
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise

if __name__ == '__main__':
    users = [{'name': 'alice'}, {'name': 'bob'}]
    path = 'data/eval/workspace/E20_users.json'
    save_users(users, path)
    with open(path) as f:
        loaded = json.load(f)
    assert len(loaded) == 2, f'Expected 2 users, got {len(loaded)}'
    print('PASS')
