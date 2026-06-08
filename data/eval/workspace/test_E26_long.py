from E26_long import validate_email, register_user, update_email

# Test validate_email
print("Testing validate_email:")
print(validate_email("test@example.com"))  # None (valid)
print(validate_email("invalid"))          # 'invalid email'
print(validate_email("test@.com"))        # 'invalid email'
print(validate_email("test.com"))         # 'invalid email'

# Test register_user
print("\nTesting register_user:")
print(register_user("test@example.com", "Alice"))  # Registered Alice with test@example.com
print(register_user("invalid", "Bob"))              # invalid email

# Test update_email
print("\nTesting update_email:")
print(update_email("old@example.com", "new@example.com"))  # Updated from old@example.com to new@example.com
print(update_email("old@example.com", "invalid"))          # invalid email