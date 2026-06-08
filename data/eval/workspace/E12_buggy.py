def check_password(pwd):
    return pwd == 'admin123'  # Fixed: case mismatch

if __name__ == '__main__':
    assert check_password('admin123') == True, 'Should accept admin123'
    print('PASS')