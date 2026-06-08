"""Tests for E31_target.py - fibonacci and is_palindrome functions."""

import pytest
from E31_target import fibonacci, is_palindrome


# ==================== fibonacci tests ====================

class TestFibonacci:
    """Tests for the fibonacci(n) function."""

    # --- Normal cases ---

    def test_fib_base_zero(self):
        """fibonacci(0) should return 0."""
        assert fibonacci(0) == 0

    def test_fib_base_one(self):
        """fibonacci(1) should return 1."""
        assert fibonacci(1) == 1

    def test_fib_small(self):
        """fibonacci for small values."""
        assert fibonacci(2) == 1
        assert fibonacci(3) == 2
        assert fibonacci(4) == 3
        assert fibonacci(5) == 5
        assert fibonacci(6) == 8
        assert fibonacci(7) == 13
        assert fibonacci(8) == 21
        assert fibonacci(9) == 34
        assert fibonacci(10) == 55

    def test_fib_medium(self):
        """fibonacci for a medium value."""
        assert fibonacci(20) == 6765
        assert fibonacci(30) == 832040

    # --- Edge cases ---

    def test_fib_large(self):
        """fibonacci for a larger value (still within Python int range)."""
        result = fibonacci(50)
        # Known: F(50) = 12586269025
        assert result == 12586269025

    def test_fib_very_large(self):
        """fibonacci for a very large value to ensure no recursion issues."""
        result = fibonacci(100)
        # F(100) = 354224848179261915075
        assert result == 354224848179261915075

    def test_fib_negative(self):
        """fibonacci with negative input should raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-1)

    def test_fib_negative_large(self):
        """fibonacci with a large negative input should raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-100)

    # --- Error cases ---

    def test_fib_float(self):
        """fibonacci with a float should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_fib_string(self):
        """fibonacci with a string should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("10")

    def test_fib_none(self):
        """fibonacci with None should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(None)

    def test_fib_list(self):
        """fibonacci with a list should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci([5])

    def test_fib_boolean(self):
        """fibonacci with a boolean should work (True=1, False=0)."""
        assert fibonacci(True) == 1
        assert fibonacci(False) == 0


# ==================== is_palindrome tests ====================

class TestIsPalindrome:
    """Tests for the is_palindrome(s) function."""

    # --- Normal cases ---

    def test_pal_single_character(self):
        """A single character is always a palindrome."""
        assert is_palindrome("a") is True

    def test_pal_simple(self):
        """Simple palindrome words."""
        assert is_palindrome("racecar") is True
        assert is_palindrome("madam") is True
        assert is_palindrome("level") is True

    def test_pal_not_palindrome(self):
        """Non-palindromic strings."""
        assert is_palindrome("hello") is False
        assert is_palindrome("world") is False
        assert is_palindrome("python") is False

    def test_pal_case_insensitive(self):
        """is_palindrome should ignore case."""
        assert is_palindrome("Racecar") is True
        assert is_palindrome("MadAm") is True
        assert is_palindrome("LEVEL") is True

    def test_pal_with_spaces(self):
        """is_palindrome should strip leading/trailing whitespace."""
        assert is_palindrome("  racecar  ") is True
        assert is_palindrome("  madam") is True
        assert is_palindrome("level  ") is True

    # --- Edge cases ---

    def test_pal_empty_string(self):
        """An empty string should be a palindrome."""
        assert is_palindrome("") is True

    def test_pal_whitespace_only(self):
        """A string of only whitespace should be a palindrome."""
        assert is_palindrome("   ") is True
        assert is_palindrome("\t\n") is True

    def test_pal_numbers(self):
        """Numeric strings can be palindromes."""
        assert is_palindrome("12321") is True
        assert is_palindrome("12345") is False

    def test_pal_mixed_alphanumeric(self):
        """Mixed alphanumeric strings."""
        assert is_palindrome("a1b1a") is True
        assert is_palindrome("a1b2a") is False

    def test_pal_special_chars(self):
        """Strings with special characters."""
        assert is_palindrome("!@#@!") is True
        assert is_palindrome("!@#$%") is False

    def test_pal_unicode(self):
        """Unicode strings should work."""
        assert is_palindrome("ñ") is True
        assert is_palindrome("été") is True
        assert is_palindrome("café") is False

    # --- Error cases ---

    def test_pal_none(self):
        """is_palindrome with None should raise AttributeError (or TypeError)."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(None)

    def test_pal_integer(self):
        """is_palindrome with an integer should raise AttributeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(12321)

    def test_pal_list(self):
        """is_palindrome with a list should work (list has .lower? no)."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome([1, 2, 1])

    def test_pal_boolean(self):
        """is_palindrome with a boolean should raise AttributeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(True)
