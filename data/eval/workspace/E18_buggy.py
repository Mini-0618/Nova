import threading

counter = 0

def increment_counter():
    global counter
    temp = counter  # BUG: race condition
    temp += 1
    counter = temp

if __name__ == '__main__':
    threads = [threading.Thread(target=increment_counter) for _ in range(100)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert counter == 100, f'Expected 100, got {counter}'
    print('PASS')