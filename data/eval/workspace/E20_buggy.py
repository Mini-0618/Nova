import json, os

import tempfile

def save_users(users, path):
    tmp = tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(path), delete=False)
    tmp_name = tmp.name
    try:
        json.dump(users, tmp)
        tmp.close()
        os.replace(tmp_name, path)
    except:
        tmp.close()
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise

if __name__ == '__main__':
    users = [{'name': 'alice'}, {'name': 'bob'}]
    path = 'data/eval/workspace/E20_users.json'
    save_users(users, path)
    with open(path) as f:
        loaded = json.load(f)
    assert len(loaded) == 2, f'Expected 2 users, got {len(loaded)}'
    print('PASS')