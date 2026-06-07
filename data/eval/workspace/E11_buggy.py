def sum_range(a, b):
    total = 0
    for i in range(a, b):  # Fixed: range(a, b) to sum from a to b-1
        total += i
    return total

if __name__ == '__main__':
    assert sum_range(1, 5) == 10, f'Expected 10, got {sum_range(1, 5)}'
    print('PASS')