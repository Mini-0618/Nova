def validate_email(email):
    if '@' not in email or '.' not in email:
        return 'invalid email'
    return None

def register_user(email, name):
    error = validate_email(email)
    if error:
        return error
    return f'Registered {name} with {email}'

def update_email(old_email, new_email):
    error = validate_email(new_email)
    if error:
        return error
    return f'Updated from {old_email} to {new_email}'
