def add(a: int, b: int) -> int:
    return a + b

def greet(name: str) -> str:
    return f'Hello, {name}'

def is_even(n: int) -> bool:
    return n % 2 == 0

if __name__ == '__main__':
    assert add(1, 2) == 3
    assert greet('World') == 'Hello, World'
    assert is_even(4) == True
    assert is_even(3) == False
    print('PASS')