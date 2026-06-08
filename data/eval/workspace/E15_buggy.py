def count_down(n):
    while n > 0:
        print(n)
        n += 1  # BUG: should be n -= 1

if __name__ == '__main__':
    count_down(3)
    print('PASS')