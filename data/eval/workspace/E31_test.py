import pytest
from E31_target import fibonacci, is_palindrome


# ========== fibonacci tests ==========

class TestFibonacciNormal:
    """Normal cases for fibonacci."""

    def test_fib_0(self):
        assert fibonacci(0) == 0

    def test_fib_1(self):
        assert fibonacci(1) == 1

    def test_fib_2(self):
        assert fibonacci(2) == 1

    def test_fib_3(self):
        assert fibonacci(3) == 2

    def test_fib_4(self):
        assert fibonacci(4) == 3

    def test_fib_5(self):
        assert fibonacci(5) == 5

    def test_fib_6(self):
        assert fibonacci(6) == 8

    def test_fib_10(self):
        assert fibonacci(10) == 55

    def test_fib_20(self):
        assert fibonacci(20) == 6765


class TestFibonacciEdge:
    """Edge cases for fibonacci."""

    def test_fib_large_n(self):
        assert fibonacci(30) == 832040

    def test_fib_returns_int(self):
        result = fibonacci(7)
        assert isinstance(result, int)


class TestFibonacciErrors:
    """Error cases for fibonacci."""

    def test_negative_n_raises_value_error(self):
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-1)

    def test_negative_large_raises_value_error(self):
        with pytest.raises(ValueError, match='n must be non-negative'):
            fibonacci(-100)


# ========== is_palindrome tests ==========

class TestIsPalindromeNormal:
    """Normal cases for is_palindrome."""

    def test_simple_palindrome(self):
        assert is_palindrome("racecar") is True

    def test_not_palindrome(self):
        assert is_palindrome("hello") is False

    def test_single_char(self):
        assert is_palindrome("a") is True

    def test_even_length_palindrome(self):
        assert is_palindrome("abba") is True

    def test_long_palindrome(self):
        assert is_palindrome("madamimadam") is True


class TestIsPalindromeCaseInsensitive:
    """Case-insensitivity tests for is_palindrome."""

    def test_uppercase_palindrome(self):
        assert is_palindrome("Racecar") is True

    def test_all_uppercase(self):
        assert is_palindrome("ABBA") is True

    def test_mixed_case_not_palindrome(self):
        assert is_palindrome("Hello") is False


class TestIsPalindromeWhitespace:
    """Whitespace handling tests for is_palindrome."""

    def test_leading_trailing_whitespace(self):
        assert is_palindrome("  racecar  ") is True

    def test_whitespace_only_not_palindrome(self):
        # whitespace gets stripped, empty string is a palindrome
        assert is_palindrome("   ") is True

    def test_palindrome_with_spaces(self):
        # spaces inside are not stripped, so "a b a" is a palindrome
        assert is_palindrome("a b a") is True


class TestIsPalindromeEdge:
    """Edge cases for is_palindrome."""

    def test_empty_string(self):
        assert is_palindrome("") is True

    def test_two_same_chars(self):
        assert is_palindrome("aa") is True

    def test_two_diff_chars(self):
        assert is_palindrome("ab") is False


class TestIsPalindromeErrors:
    """Error cases for is_palindrome."""

    def test_integer_input(self):
        with pytest.raises(AttributeError):
            is_palindrome(12321)

    def test_none_input(self):
        with pytest.raises(AttributeError):
            is_palindrome(None)

    def test_list_input(self):
        with pytest.raises(AttributeError):
            is_palindrome([1, 2, 1])
