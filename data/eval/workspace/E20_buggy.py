import json, os

def save_users(users, path):
    with open(path, 'w') as f:  # BUG: not atomic, partial write on crash
        json.dump(users, f)

if __name__ == '__main__':
    users = [{'name': 'alice'}, {'name': 'bob'}]
    path = 'data/eval/workspace/E20_users.json'
    save_users(users, path)
    with open(path) as f:
        loaded = json.load(f)
    assert len(loaded) == 2, f'Expected 2 users, got {len(loaded)}'
    print('PASS')