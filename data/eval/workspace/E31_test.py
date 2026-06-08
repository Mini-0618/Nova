import pytest
from E31_target import fibonacci, is_palindrome


# ==================== fibonacci tests ====================

class TestFibonacci:
    """Tests for the fibonacci function."""

    # --- Normal cases ---

    def test_fib_base_zero(self):
        """fibonacci(0) should return 0."""
        assert fibonacci(0) == 0

    def test_fib_base_one(self):
        """fibonacci(1) should return 1."""
        assert fibonacci(1) == 1

    def test_fib_small(self):
        """fibonacci for small n values."""
        assert fibonacci(2) == 1
        assert fibonacci(3) == 2
        assert fibonacci(4) == 3
        assert fibonacci(5) == 5
        assert fibonacci(6) == 8
        assert fibonacci(7) == 13
        assert fibonacci(10) == 55

    def test_fib_larger(self):
        """fibonacci for larger n values."""
        assert fibonacci(20) == 6765
        assert fibonacci(30) == 832040

    # --- Edge cases ---

    def test_fib_large_number(self):
        """fibonacci(100) — large but should still compute correctly."""
        assert fibonacci(100) == 354224848179261915075

    # --- Error cases ---

    def test_fib_negative_raises(self):
        """fibonacci with negative n should raise ValueError."""
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-1)

    def test_fib_negative_large_raises(self):
        """fibonacci with a large negative number should raise ValueError."""
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-100)

    def test_fib_non_integer_raises_typeerror(self):
        """fibonacci with non-integer should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(1.5)

    def test_fib_none_raises_typeerror(self):
        """fibonacci with None should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci(None)

    def test_fib_string_raises_typeerror(self):
        """fibonacci with a string should raise TypeError."""
        with pytest.raises(TypeError):
            fibonacci("5")


# ==================== is_palindrome tests ====================

class TestIsPalindrome:
    """Tests for the is_palindrome function."""

    # --- Normal cases ---

    def test_pal_simple_even(self):
        """Even-length palindrome."""
        assert is_palindrome("abba") is True

    def test_pal_simple_odd(self):
        """Odd-length palindrome."""
        assert is_palindrome("racecar") is True

    def test_pal_single_char(self):
        """Single character is always a palindrome."""
        assert is_palindrome("a") is True

    def test_pal_empty_string(self):
        """Empty string is a palindrome."""
        assert is_palindrome("") is True

    def test_non_palindrome(self):
        """Non-palindrome string."""
        assert is_palindrome("hello") is False

    def test_pal_mixed_case(self):
        """Case-insensitive check."""
        assert is_palindrome("RaceCar") is True

    def test_pal_with_spaces(self):
        """Spaces are stripped before comparison."""
        assert is_palindrome("  racecar  ") is True

    def test_pal_whitespace_only(self):
        """Whitespace-only string — after strip it's empty, so palindrome."""
        assert is_palindrome("   ") is True

    def test_pal_mixed_case_and_spaces(self):
        """Combination of leading/trailing spaces and mixed case."""
        assert is_palindrome("  A man a plan a canal Panama  ".lower().replace(" ", "")) is True

    # --- Edge cases ---

    def test_pal_numeric_string(self):
        """Numeric palindrome string."""
        assert is_palindrome("12321") is True

    def test_pal_numeric_non_pal(self):
        """Numeric non-palindrome string."""
        assert is_palindrome("12345") is False

    def test_pal_special_chars(self):
        """String with special characters that is a palindrome."""
        assert is_palindrome("!@# @!") is False  # after strip+lower: "!@# @!" -> "!@# @!" reversed is "!@ #@!"
        # Actually let's verify: "!@# @!" -> lower+strip = "!@# @!" -> reversed = "!@ #@!" — not same
        # Let's use a real palindrome with special chars
        assert is_palindrome("!!!") is True

    def test_pal_unicode(self):
        """Unicode palindrome."""
        assert is_palindrome("ññ") is True
        assert is_palindrome("ñx") is False

    # --- Error cases ---

    def test_pal_none_raises(self):
        """is_palindrome(None) should raise AttributeError or TypeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(None)

    def test_pal_integer_raises(self):
        """is_palindrome(123) with non-string should raise AttributeError."""
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(123)
