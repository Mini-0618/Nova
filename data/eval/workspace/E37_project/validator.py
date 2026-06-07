import re


def validate_email(email):
    """Validate an email address using a regex pattern."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+$'
    return bool(re.match(pattern, email))
