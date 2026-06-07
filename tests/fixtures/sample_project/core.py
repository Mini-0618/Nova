"""Sample core module for testing."""

from . import utils


def process_data(data):
    """Process data using utils."""
    result = utils.helper_b()
    return result + len(data)


def main():
    """Main entry that calls process_data."""
    data = [1, 2, 3]
    return process_data(data)
