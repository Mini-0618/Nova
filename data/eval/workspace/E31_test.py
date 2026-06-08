"""Tests for E31_target.py — fibonacci and is_palindrome functions."""

import pytest
from E31_target import fibonacci, is_palindrome


# =====================
# Tests for fibonacci
# =====================

class TestFibonacci:
    """Tests for the fibonacci(n) function."""

    # --- Normal cases ---

    def test_fib_zero(self):
        """fibonacci(0) should return 0."""
        assert fibonacci(0) == 0

    def test_fib_one(self):
        """fibonacci(1) should return 1."""
        assert fibonacci(1) == 1

    def test_fib_small_numbers(self):
        """fibonacci for small n values."""
        assert fibonacci(2) == 1
        assert fibonacci(3) == 2
        assert fibonacci(4) == 3
        assert fibonacci(5) == 5
        assert fibonacci(6) == 8
        assert fibonacci(7) == 13
        assert fibonacci(8) == 21
        assert fibonacci(9) == 34
        assert fibonacci(10) == 55

    def test_fib_medium_number(self):
        """fibonacci for a medium-sized n."""
        assert fibonacci(20) == 6765
        assert fibonacci(30) == 832040

    # --- Edge cases ---

    def test_fib_large_number(self):
        """fibonacci for a larger n (within reasonable range)."""
        result = fibonacci(50)
        # Known value: fib(50) = 12586269025
        assert result == 12586269025

    def test_fib_very_large(self):
        """fibonacci for n=100 (big integer)."""
        result = fibonacci(100)
        expected = 354224848179261915075
        assert result == expected

    def test_fib_consecutive_relationship(self):
        """Verify fib(n+1) >= fib(n) for monotonicity."""
        prev = -1
        for n in range(0, 20):
            cur = fibonacci(n)
            assert cur >= prev
            prev = cur

    # --- Error cases ---

    def test_fib_negative_raises_value_error(self):
        """fibonacci with negative n should raise ValueError."""
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-1)

    def test_fib_negative_large_raises_value_error(self):
        """fibonacci with a large negative n should raise ValueError."""
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-100)

    def test_fib_float_raises_type_error(self):
        """fibonacci with a float should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_fib_string_raises_type_error(self):
        """fibonacci with a string should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("10")

    def test_fib_none_raises_type_error(self):
        """fibonacci with None should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(None)


# =====================
# Tests for is_palindrome
# =====================

class TestIsPalindrome:
    """Tests for the is_palindrome(s) function."""

    # --- Normal cases ---

    def test_palindrome_simple(self):
        """Simple palindrome word."""
        assert is_palindrome("racecar") is True

    def test_palindrome_another(self):
        """Another palindrome word."""
        assert is_palindrome("madam") is True

    def test_non_palindrome(self):
        """Non-palindrome word should return False."""
        assert is_palindrome("hello") is False

    def test_palindrome_numeric_string(self):
        """Numeric palindrome string."""
        assert is_palindrome("12321") is True

    def test_non_palindrome_numeric(self):
        """Non-palindrome numeric string."""
        assert is_palindrome("12345") is False

    # --- Case insensitivity ---

    def test_palindrome_mixed_case(self):
        """is_palindrome should be case-insensitive."""
        assert is_palindrome("Racecar") is True
        assert is_palindrome("MadAm") is True

    def test_palindrome_uppercase(self):
        """All-uppercase palindrome."""
        assert is_palindrome("RACECAR") is True

    # --- Whitespace handling ---

    def test_palindrome_with_leading_trailing_spaces(self):
        """is_palindrome should strip leading/trailing whitespace."""
        assert is_palindrome("  racecar  ") is True
        assert is_palindrome("  madam  ") is True

    def test_palindrome_with_tabs(self):
        """is_palindrome should strip tabs."""
        assert is_palindrome("\tracecar\t") is True

    def test_palindrome_with_newlines(self):
        """is_palindrome should strip newlines."""
        assert is_palindrome("\nracecar\n") is True

    # --- Edge cases ---

    def test_empty_string(self):
        """Empty string should be a palindrome."""
        assert is_palindrome("") is True

    def test_single_character(self):
        """Single character should be a palindrome."""
        assert is_palindrome("a") is True
        assert is_palindrome("Z") is True

    def test_single_space(self):
        """Single space (after strip becomes empty) should be a palindrome."""
        assert is_palindrome(" ") is True

    def test_whitespace_only(self):
        """Whitespace-only string (after strip becomes empty) should be a palindrome."""
        assert is_palindrome("   ") is True

    def test_special_characters(self):
        """Palindrome with special characters."""
        assert is_palindrome("!@#@!") is True
        assert is_palindrome("!@#") is False

    def test_unicode_palindrome(self):
        """Palindrome with unicode characters."""
        assert is_palindrome("ñ") is True
        assert is_palindrome("aña") is True
        assert is_palindrome("abcñcba") is True

    def test_two_different_chars(self):
        """Two different characters should not be a palindrome."""
        assert is_palindrome("ab") is False

    def test_two_same_chars(self):
        """Two identical characters should be a palindrome."""
        assert is_palindrome("aa") is True

    def test_even_length_palindrome(self):
        """Even-length palindrome."""
        assert is_palindrome("abba") is True

    def test_odd_length_palindrome(self):
        """Odd-length palindrome."""
        assert is_palindrome("abcba") is True

    # --- Error cases ---

    def test_none_raises_type_error(self):
        """is_palindrome with None should raise TypeError."""
        with pytest.raises(TypeError):
            is_palindrome(None)

    def test_integer_raises_type_error(self):
        """is_palindrome with an integer should raise TypeError."""
        with pytest.raises(TypeError):
            is_palindrome(12321)
