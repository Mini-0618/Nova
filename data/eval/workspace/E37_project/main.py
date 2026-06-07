from validator import validate_email

assert validate_email('test@example.com') == True
assert validate_email('invalid') == False
assert validate_email('a@b.c') == True
print('PASS')