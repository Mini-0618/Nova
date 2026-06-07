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


# Module-level instance for backward compatibility with the standalone function API
_counter = Counter()


def increment():
    _counter.increment()


def decrement():
    _counter.decrement()


def get_count():
    return _counter.get_count()


def reset():
    _counter.reset()


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
