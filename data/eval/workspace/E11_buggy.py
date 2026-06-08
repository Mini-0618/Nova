def sum_range(a, b):
    total = 0
    for i in range(a, b):  # FIXED: range(a, b) excludes b, so sum_range(1,5) = 1+2+3+4 = 10
        total += i
    return total

if __name__ == '__main__':
    assert sum_range(1, 5) == 10, f'Expected 10, got {sum_range(1, 5)}'
    print('PASS')