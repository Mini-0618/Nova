"""Comprehensive pytest tests for E31_target.py.

Covers:
- fibonacci: normal cases, edge cases, error cases
- is_palindrome: normal cases, edge cases, error cases
"""

import pytest
from E31_target import fibonacci, is_palindrome


# ============================================================
# Tests for fibonacci(n)
# ============================================================

class TestFibonacci:
    """Test suite for fibonacci(n)."""

    # --- Normal cases ---

    @pytest.mark.parametrize("n, expected", [
        (0, 0),
        (1, 1),
        (2, 1),
        (3, 2),
        (4, 3),
        (5, 5),
        (6, 8),
        (7, 13),
        (8, 21),
        (9, 34),
        (10, 55),
        (20, 6765),
        (30, 832040),
    ])
    def test_normal(self, n, expected):
        assert fibonacci(n) == expected

    # --- Edge cases ---

    def test_zero(self):
        """Boundary: n=0 should return 0."""
        assert fibonacci(0) == 0

    def test_one(self):
        """Boundary: n=1 should return 1."""
        assert fibonacci(1) == 1

    def test_large_value(self):
        """Verify large Fibonacci number (n=100)."""
        result = fibonacci(100)
        # F(100) = 354224848179261915075
        assert result == 354224848179261915075

    def test_large_value_200(self):
        """Verify n=200 returns a large integer without overflow."""
        result = fibonacci(200)
        assert result > 10**40
        # Verify it's the correct value using known properties
        # F(200) mod 10 = 5 (since F(n) mod 10 cycles every 60)
        assert result % 10 == 5

    # --- Error cases ---

    def test_negative_raises_value_error(self):
        """Negative input should raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-1)

    def test_negative_large_raises_value_error(self):
        """Large negative input should also raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-100)

    def test_float_input_raises_type_error(self):
        """Float input should raise TypeError (not handled, but expected)."""
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_string_input_raises_type_error(self):
        """String input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("10")

    def test_none_input_raises_type_error(self):
        """None input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(None)


# ============================================================
# Tests for is_palindrome(s)
# ============================================================

class TestIsPalindrome:
    """Test suite for is_palindrome(s)."""

    # --- Normal cases ---

    @pytest.mark.parametrize("s, expected", [
        ("", True),             # empty string
        ("a", True),            # single character
        ("aa", True),           # two same chars
        ("ab", False),          # two different chars
        ("aba", True),          # odd-length palindrome
        ("abba", True),         # even-length palindrome
        ("abc", False),         # non-palindrome
        ("racecar", True),      # common palindrome
        ("hello", False),       # non-palindrome
        ("Madam", True),        # case-insensitive
        ("RaceCar", True),      # mixed case
        ("A man a plan a canal Panama", False),  # spaces break palindrome
    ])
    def test_normal(self, s, expected):
        assert is_palindrome(s) == expected

    # --- Edge cases ---

    def test_whitespace_handling(self):
        """Leading/trailing whitespace should be stripped."""
        assert is_palindrome("  aba  ") is True
        assert is_palindrome("  hello  ") is False

    def test_case_insensitivity(self):
        """Should ignore case differences."""
        assert is_palindrome("Noon") is True
        assert is_palindrome("Deified") is True

    def test_mixed_whitespace_and_case(self):
        """Combination of whitespace and case."""
        assert is_palindrome("  RaceCar  ") is True

    def test_special_characters(self):
        """Strings with punctuation or special chars."""
        assert is_palindrome("!@#") is False
        assert is_palindrome("!!!") is True

    def test_numbers(self):
        """Numeric strings."""
        assert is_palindrome("12321") is True
        assert is_palindrome("12345") is False

    def test_unicode(self):
        """Unicode characters should work (comparison is direct)."""
        assert is_palindrome("ñ") is True
        assert is_palindrome("abañaba") is True
        assert is_palindrome("ñandú") is False

    def test_very_long_string(self):
        """Long palindrome string."""
        long_pal = "a" * 10000
        assert is_palindrome(long_pal) is True
        long_non = "a" * 9999 + "b"
        assert is_palindrome(long_non) is False

    # --- Error cases ---

    def test_none_input_raises_attribute_error(self):
        """None input should raise AttributeError (s.lower() fails)."""
        with pytest.raises(AttributeError):
            is_palindrome(None)

    def test_integer_input_raises_attribute_error(self):
        """Integer input should raise AttributeError."""
        with pytest.raises(AttributeError):
            is_palindrome(12321)

    def test_list_input_raises_attribute_error(self):
        """List input should raise AttributeError."""
        with pytest.raises(AttributeError):
            is_palindrome(["a", "b", "a"])

    def test_boolean_input_raises_attribute_error(self):
        """Boolean input should raise AttributeError."""
        with pytest.raises(AttributeError):
            is_palindrome(True)
