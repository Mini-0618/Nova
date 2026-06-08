import pytest
from E31_target import fibonacci, is_palindrome


# ============================================================
# Tests for fibonacci(n)
# ============================================================

class TestFibonacci:
    """Tests for the fibonacci function."""

    # --- Normal cases ---

    def test_fib_zero(self):
        assert fibonacci(0) == 0

    def test_fib_one(self):
        assert fibonacci(1) == 1

    def test_fib_small(self):
        assert fibonacci(2) == 1
        assert fibonacci(3) == 2
        assert fibonacci(4) == 3
        assert fibonacci(5) == 5
        assert fibonacci(6) == 8
        assert fibonacci(7) == 13
        assert fibonacci(8) == 21
        assert fibonacci(9) == 34
        assert fibonacci(10) == 55

    def test_fib_larger(self):
        assert fibonacci(20) == 6765
        assert fibonacci(30) == 832040

    # --- Edge cases ---

    def test_fib_large_number(self):
        # Verify it handles moderately large values without overflow
        result = fibonacci(100)
        assert result == 354224848179261915075

    def test_fib_consecutive_property(self):
        # fib(n+1) should be >= fib(n) for non-negative n
        for n in range(1, 20):
            assert fibonacci(n + 1) >= fibonacci(n)

    # --- Error cases ---

    def test_fib_negative_raises_value_error(self):
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-1)

    def test_fib_negative_large_raises_value_error(self):
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-100)

    def test_fib_non_integer_raises_type_error(self):
        with pytest.raises(TypeError):
            fibonacci(1.5)

    def test_fib_string_raises_type_error(self):
        with pytest.raises(TypeError):
            fibonacci("5")


# ============================================================
# Tests for is_palindrome(s)
# ============================================================

class TestIsPalindrome:
    """Tests for the is_palindrome function."""

    # --- Normal cases ---

    def test_palindrome_simple_word(self):
        assert is_palindrome("racecar") is True

    def test_palindrome_even_length(self):
        assert is_palindrome("abba") is True

    def test_palindrome_single_character(self):
        assert is_palindrome("a") is True

    def test_not_palindrome(self):
        assert is_palindrome("hello") is False

    def test_palindrome_case_insensitive(self):
        assert is_palindrome("Racecar") is True

    def test_palindrome_mixed_case(self):
        assert is_palindrome("Aba") is True

    # --- Edge cases ---

    def test_palindrome_empty_string(self):
        assert is_palindrome("") is True

    def test_palindrome_with_spaces(self):
        assert is_palindrome("  racecar  ") is True

    def test_palindrome_with_leading_trailing_spaces(self):
        assert is_palindrome("  abba  ") is True

    def test_not_palindrome_with_spaces(self):
        assert is_palindrome("  hello  ") is False

    def test_palindrome_numbers_as_string(self):
        assert is_palindrome("12321") is True

    def test_not_palindrome_numbers_as_string(self):
        assert is_palindrome("12345") is False

    def test_palindrome_special_characters(self):
        assert is_palindrome("!@#@!") is True

    def test_palindrome_unicode(self):
        assert is_palindrome("ñ") is True

    def test_palindrome_with_only_spaces(self):
        # After strip, this becomes "" which is palindrome
        assert is_palindrome("   ") is True

    # --- Error cases ---

    def test_palindrome_none_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            is_palindrome(None)

    def test_palindrome_integer_raises_attribute_error(self):
        with pytest.raises(AttributeError):
            is_palindrome(12321)
