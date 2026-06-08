users = {'alice': 30, 'bob': 25}

def get_user_age(name):
    return users.get(name, -1)  # FIXED: return -1 if key not found

if __name__ == '__main__':
    assert get_user_age('alice') == 30
    assert get_user_age('unknown') == -1
    print('PASS')