"""Tests for E31_target.py - fibonacci and is_palindrome functions."""

import pytest
from E31_target import fibonacci, is_palindrome


# =============================================================================
# Tests for fibonacci(n)
# =============================================================================

class TestFibonacci:
    """Test suite for the fibonacci function."""

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
        (15, 610),
        (20, 6765),
        (25, 75025),
        (30, 832040),
    ])
    def test_normal_cases(self, n, expected):
        """Test fibonacci with standard positive inputs."""
        assert fibonacci(n) == expected

    # --- Edge cases ---

    def test_zero(self):
        """Edge case: fibonacci(0) should return 0."""
        assert fibonacci(0) == 0

    def test_one(self):
        """Edge case: fibonacci(1) should return 1."""
        assert fibonacci(1) == 1

    def test_large_number(self):
        """Edge case: fibonacci with a moderately large input."""
        # F(35) = 9227465
        assert fibonacci(35) == 9227465
        # F(40) = 102334155
        assert fibonacci(40) == 102334155

    # --- Error cases ---

    def test_negative_value_error(self):
        """Error case: negative input should raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-1)

    def test_negative_large_value_error(self):
        """Error case: large negative input should also raise ValueError."""
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-100)

    def test_float_input_type_error(self):
        """Error case: float input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_string_input_type_error(self):
        """Error case: string input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("10")

    def test_none_input_type_error(self):
        """Error case: None input should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(None)


# =============================================================================
# Tests for is_palindrome(s)
# =============================================================================

class TestIsPalindrome:
    """Test suite for the is_palindrome function."""

    # --- Normal cases ---

    @pytest.mark.parametrize("s, expected", [
        ("racecar", True),
        ("hello", False),
        ("madam", True),
        ("python", False),
        ("a", True),
        ("", True),
    ])
    def test_normal_cases(self, s, expected):
        """Test is_palindrome with standard string inputs."""
        assert is_palindrome(s) == expected

    # --- Edge cases ---

    def test_case_insensitivity(self):
        """Edge case: should be case-insensitive."""
        assert is_palindrome("Racecar") is True
        assert is_palindrome("MADAM") is True
        assert is_palindrome("Hello") is False

    def test_whitespace_stripping(self):
        """Edge case: leading/trailing whitespace should be stripped."""
        assert is_palindrome("  racecar  ") is True
        assert is_palindrome("  madam  ") is True
        assert is_palindrome("  hello  ") is False

    def test_empty_string(self):
        """Edge case: empty string is a palindrome."""
        assert is_palindrome("") is True

    def test_single_character(self):
        """Edge case: single character is always a palindrome."""
        assert is_palindrome("a") is True
        assert is_palindrome("Z") is True

    def test_mixed_case_and_spaces(self):
        """Edge case: mixed case with surrounding whitespace."""
        assert is_palindrome("  Racecar  ") is True
        assert is_palindrome("  Hello  ") is False

    def test_special_characters(self):
        """Edge case: strings with punctuation/special characters."""
        assert is_palindrome("12321") is True
        assert is_palindrome("!!") is True
        assert is_palindrome("!@#@!") is True
        assert is_palindrome("!@#") is False

    def test_whitespace_only(self):
        """Edge case: whitespace-only strings are palindromes after strip (becomes empty)."""
        assert is_palindrome("   ") is True
        assert is_palindrome("\t\n") is True

    # --- Error cases ---

    def test_non_string_input(self):
        """Error case: non-string input should raise AttributeError or TypeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(123)

    def test_none_input(self):
        """Error case: None input should raise AttributeError or TypeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(None)

    def test_list_input(self):
        """Error case: list input should raise AttributeError or TypeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(["r", "a", "c", "e", "c", "a", "r"])
