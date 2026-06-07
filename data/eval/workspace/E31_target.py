def fibonacci(n):
    if n < 0:
        raise ValueError('n must be non-negative')
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

def is_palindrome(s):
    s = s.lower().strip()
    return s == s[::-1]