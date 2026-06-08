class Counter:
    def __init__(self):
        self.count = 0

    def increment(self):
        self.count += 1

    def decrement(self):
        self.count -= 1

    def get_count(self):
        return self.count

    def reset(self):
        self.count = 0

if __name__ == '__main__':
    c = Counter()
    c.reset()
    c.increment()
    c.increment()
    assert c.get_count() == 2
    c.decrement()
    assert c.get_count() == 1
    c.reset()
    assert c.get_count() == 0
    print('PASS')
