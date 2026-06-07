import json, os

def save_users(users, path):
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(users, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)

if __name__ == '__main__':
    users = [{'name': 'alice'}, {'name': 'bob'}]
    path = 'data/eval/workspace/E20_users.json'
    save_users(users, path)
    with open(path) as f:
        loaded = json.load(f)
    assert len(loaded) == 2, f'Expected 2 users, got {len(loaded)}'
    print('PASS')