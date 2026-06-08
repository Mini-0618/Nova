def validate_email(email):
    if '@' not in email or '.' not in email:
        return False
    return True

def register_user(email, name):
    if not validate_email(email):
        return 'invalid email'
    return f'Registered {name} with {email}'

def update_email(old_email, new_email):
    if not validate_email(new_email):
        return 'invalid email'
    return f'Updated from {old_email} to {new_email}'