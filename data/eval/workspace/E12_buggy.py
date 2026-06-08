def check_password(pwd):
    return pwd.lower() == 'admin123'  # FIX: case-insensitive comparison

if __name__ == '__main__':
    assert check_password('admin123') == True, 'Should accept admin123'
    print('PASS')