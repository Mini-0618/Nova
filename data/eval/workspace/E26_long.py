def validate_email(email):
    if '@' not in email or '.' not in email:
        return 'invalid email'
    return None

def register_user(email, name):
    result = validate_email(email)
    if result:
        return result
    return f'Registered {name} with {email}'

def update_email(old_email, new_email):
    result = validate_email(new_email)
    if result:
        return result
    return f'Updated from {old_email} to {new_email}'