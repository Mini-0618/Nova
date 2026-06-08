def check_password(pwd):
    return pwd == 'Admin123'  # BUG: case mismatch

if __name__ == '__main__':
    assert check_password('admin123') == True, 'Should accept admin123'
    print('PASS')