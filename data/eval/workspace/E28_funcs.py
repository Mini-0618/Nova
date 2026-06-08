count = 0

def increment():
    global count
    count += 1

def decrement():
    global count
    count -= 1

def get_count():
    return count

def reset():
    global count
    count = 0

if __name__ == '__main__':
    reset()
    increment()
    increment()
    assert get_count() == 2
    decrement()
    assert get_count() == 1
    reset()
    assert get_count() == 0
    print('PASS')