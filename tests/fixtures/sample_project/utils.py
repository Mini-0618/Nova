"""Sample utils module for testing."""


def helper_a():
    """A helper that calls nothing."""
    return 42


def helper_b():
    """A helper that calls helper_a."""
    return helper_a() + 1


def helper_c(x):
    """A helper that calls helper_a and helper_b."""
    a = helper_a()
    b = helper_b()
    return a + b + x
