def count_down(n):
    while n > 0:
        print(n)
        n -= 1  # Fixed: was n += 1 causing infinite loop

if __name__ == '__main__':
    count_down(3)
    print('PASS')