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
    counter = Counter()
    counter.increment()
    counter.increment()
    assert counter.get_count() == 2
    counter.decrement()
    assert counter.get_count() == 1
    counter.reset()
    assert counter.get_count() == 0
    print('PASS')
