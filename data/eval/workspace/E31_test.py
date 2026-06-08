"""Comprehensive test suite for E31_target.py using pytest.

Tests cover:
- fibonacci: normal cases, edge cases (0, 1), large values, error cases (negative input)
- is_palindrome: normal cases, case insensitivity, whitespace handling, edge cases (empty, single char), non-palindromes
"""

import pytest
from E31_target import fibonacci, is_palindrome


# =============================================================================
# Tests for fibonacci(n)
# =============================================================================

class TestFibonacci:
    """Test suite for the fibonacci function."""

    # --- Normal cases ---

    def test_fibonacci_small_values(self):
        """Test fibonacci for small known values."""
        assert fibonacci(0) == 0
        assert fibonacci(1) == 1
        assert fibonacci(2) == 1
        assert fibonacci(3) == 2
        assert fibonacci(4) == 3
        assert fibonacci(5) == 5
        assert fibonacci(6) == 8
        assert fibonacci(7) == 13
        assert fibonacci(8) == 21
        assert fibonacci(9) == 34
        assert fibonacci(10) == 55

    def test_fibonacci_larger_values(self):
        """Test fibonacci for larger inputs."""
        assert fibonacci(20) == 6765
        assert fibonacci(30) == 832040
        assert fibonacci(35) == 9227465

    # --- Edge cases ---

    def test_fibonacci_zero(self):
        """Edge case: fibonacci(0) should return 0."""
        assert fibonacci(0) == 0

    def test_fibonacci_one(self):
        """Edge case: fibonacci(1) should return 1."""
        assert fibonacci(1) == 1

    def test_fibonacci_two(self):
        """Edge case: fibonacci(2) should return 1."""
        assert fibonacci(2) == 1

    # --- Error cases ---

    def test_fibonacci_negative_raises_value_error(self):
        """Error case: negative input should raise ValueError."""
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-1)

    def test_fibonacci_large_negative_raises_value_error(self):
        """Error case: large negative input should raise ValueError."""
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-100)

    def test_fibonacci_invalid_type_raises_type_error(self):
        """Error case: non-integer input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("string")
        with pytest.raises(TypeError):
            fibonacci(3.14)
        with pytest.raises(TypeError):
            fibonacci(None)


# =============================================================================
# Tests for is_palindrome(s)
# =============================================================================

class TestIsPalindrome:
    """Test suite for the is_palindrome function."""

    # --- Normal cases ---

    def test_is_palindrome_simple(self):
        """Test simple palindromes."""
        assert is_palindrome("racecar") is True
        assert is_palindrome("madam") is True
        assert is_palindrome("level") is True
        assert is_palindrome("radar") is True

    def test_is_palindrome_not_palindrome(self):
        """Test that non-palindromes return False."""
        assert is_palindrome("hello") is False
        assert is_palindrome("world") is False
        assert is_palindrome("python") is False

    # --- Case insensitivity ---

    def test_is_palindrome_case_insensitive(self):
        """Test that palindrome detection is case-insensitive."""
        assert is_palindrome("Racecar") is True
        assert is_palindrome("MadAm") is True
        assert is_palindrome("RADAR") is True

    def test_is_palindrome_mixed_case(self):
        """Test palindromes with mixed casing."""
        assert is_palindrome("Aba") is True
        assert is_palindrome("Noon") is True

    # --- Whitespace handling ---

    def test_is_palindrome_with_whitespace(self):
        """Test palindromes with leading/trailing whitespace."""
        assert is_palindrome("  racecar  ") is True
        assert is_palindrome("  madam") is True
        assert is_palindrome("level  ") is True

    def test_is_palindrome_whitespace_only(self):
        """Edge case: whitespace-only strings are palindromes."""
        assert is_palindrome("   ") is True
        assert is_palindrome(" ") is True
        assert is_palindrome("") is True

    # --- Edge cases ---

    def test_is_palindrome_empty_string(self):
        """Edge case: empty string is a palindrome."""
        assert is_palindrome("") is True

    def test_is_palindrome_single_character(self):
        """Edge case: single character is a palindrome."""
        assert is_palindrome("a") is True
        assert is_palindrome("Z") is True
        assert is_palindrome("1") is True

    def test_is_palindrome_numbers(self):
        """Test palindromes with numeric strings."""
        assert is_palindrome("12321") is True
        assert is_palindrome("12345") is False
        assert is_palindrome("1001") is True

    def test_is_palindrome_special_characters(self):
        """Test palindromes with special characters."""
        assert is_palindrome("!@#@!") is True
        assert is_palindrome("!@#$%") is False

    # --- Error cases ---

    def test_is_palindrome_non_string_input(self):
        """Error case: non-string input should raise AttributeError or TypeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(12321)
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(None)
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(True)
