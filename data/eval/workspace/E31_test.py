"""Comprehensive tests for E31_target.py using pytest."""

import pytest
from E31_target import fibonacci, is_palindrome


# ========== Fibonacci Tests ==========

class TestFibonacci:
    """Tests for the fibonacci function."""

    # --- Normal Cases ---
    def test_fib_zero(self):
        """F(0) should return 0."""
        assert fibonacci(0) == 0

    def test_fib_one(self):
        """F(1) should return 1."""
        assert fibonacci(1) == 1

    def test_fib_two(self):
        """F(2) = 0 + 1 = 1."""
        assert fibonacci(2) == 1

    def test_fib_three(self):
        """F(3) = 1 + 1 = 2."""
        assert fibonacci(3) == 2

    def test_fib_five(self):
        """F(5) = 5."""
        assert fibonacci(5) == 5

    def test_fib_ten(self):
        """F(10) = 55."""
        assert fibonacci(10) == 55

    def test_fib_twenty(self):
        """F(20) = 6765."""
        assert fibonacci(20) == 6765

    # --- Edge Cases ---
    def test_fib_large_number(self):
        """Test a moderately large input to ensure no recursion/overflow issues."""
        # F(100) = 354224848179261915075
        assert fibonacci(100) == 354224848179261915075

    def test_fib_consecutive_values(self):
        """Verify the recurrence relation holds for consecutive values."""
        for n in range(2, 20):
            assert fibonacci(n) == fibonacci(n - 1) + fibonacci(n - 2)

    # --- Error Cases ---
    def test_fib_negative_raises_value_error(self):
        """Negative input should raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-1)

    def test_fib_large_negative_raises_value_error(self):
        """Large negative input should also raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-100)

    def test_fib_float_raises_type_error(self):
        """Float input should raise TypeError (since range() expects int)."""
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_fib_string_raises_type_error(self):
        """String input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("10")

    def test_fib_none_raises_type_error(self):
        """None input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(None)


# ========== Palindrome Tests ==========

class TestIsPalindrome:
    """Tests for the is_palindrome function."""

    # --- Normal Cases ---
    def test_pal_simple_even(self):
        """Even-length palindrome."""
        assert is_palindrome("abba") is True

    def test_pal_simple_odd(self):
        """Odd-length palindrome."""
        assert is_palindrome("racecar") is True

    def test_pal_single_character(self):
        """Single character is always a palindrome."""
        assert is_palindrome("a") is True

    def test_pal_empty_string(self):
        """Empty string is a palindrome."""
        assert is_palindrome("") is True

    def test_non_pal_simple(self):
        """Simple non-palindrome."""
        assert is_palindrome("hello") is False

    def test_non_pal_different_case(self):
        """Case-insensitive check: 'Racecar' should be True."""
        assert is_palindrome("Racecar") is True

    def test_pal_with_spaces(self):
        """String with surrounding spaces — strip removes them."""
        assert is_palindrome("  racecar  ") is True

    def test_pal_uppercase(self):
        """All uppercase palindrome."""
        assert is_palindrome("MADAM") is True

    def test_pal_mixed_case(self):
        """Mixed-case palindrome."""
        assert is_palindrome("MadAm") is True

    # --- Edge Cases ---
    def test_pal_with_leading_trailing_spaces(self):
        """String with only spaces after stripping becomes empty."""
        assert is_palindrome("   ") is True  # strip -> "" -> palindrome

    def test_pal_tabs_and_newlines(self):
        """String with whitespace characters that get stripped."""
        assert is_palindrome("\t\n") is True  # strip -> "" -> palindrome

    def test_non_pal_with_spaces(self):
        """Non-palindrome with surrounding spaces."""
        assert is_palindrome("  notapal  ") is False

    def test_pal_numbers(self):
        """Numeric string palindrome."""
        assert is_palindrome("12321") is True

    def test_non_pal_numbers(self):
        """Non-palindrome numeric string."""
        assert is_palindrome("12345") is False

    def test_pal_special_chars(self):
        """Palindrome with special characters."""
        assert is_palindrome("!@#@!") is True

    def test_pal_unicode(self):
        """Unicode palindrome."""
        assert is_palindrome("aña") is True

    def test_pal_repeated_char(self):
        """Repeated same character."""
        assert is_palindrome("aaaa") is True

    # --- Error Cases ---
    def test_pal_none_raises_attribute_error(self):
        """None input should raise AttributeError (no .lower())."""
        with pytest.raises(AttributeError):
            is_palindrome(None)

    def test_pal_integer_raises_attribute_error(self):
        """Integer input should raise AttributeError."""
        with pytest.raises(AttributeError):
            is_palindrome(12321)

    def test_pal_list_raises_attribute_error(self):
        """List input should raise AttributeError."""
        with pytest.raises(AttributeError):
            is_palindrome(["a", "b", "a"])
