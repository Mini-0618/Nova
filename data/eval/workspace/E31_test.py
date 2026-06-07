import pytest
from E31_target import fibonacci, is_palindrome


class TestFibonacci:
    """Tests for the fibonacci function."""

    # Normal cases
    def test_fibonacci_0(self):
        assert fibonacci(0) == 0

    def test_fibonacci_1(self):
        assert fibonacci(1) == 1

    def test_fibonacci_2(self):
        assert fibonacci(2) == 1

    def test_fibonacci_3(self):
        assert fibonacci(3) == 2

    def test_fibonacci_4(self):
        assert fibonacci(4) == 3

    def test_fibonacci_5(self):
        assert fibonacci(5) == 5

    def test_fibonacci_6(self):
        assert fibonacci(6) == 8

    def test_fibonacci_10(self):
        assert fibonacci(10) == 55

    def test_fibonacci_20(self):
        assert fibonacci(20) == 6765

    # Larger values
    def test_fibonacci_30(self):
        assert fibonacci(30) == 832040

    # Edge cases
    def test_fibonacci_negative_raises_error(self):
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-1)

    def test_fibonacci_negative_large_raises_error(self):
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-100)

    def test_fibonacci_returns_int(self):
        assert isinstance(fibonacci(10), int)

    # Error cases
    def test_fibonacci_float_truncated(self):
        # Floats like 5.0 should work because range accepts them, 
        # but the user should pass int.
        # Actually, range() requires int, so 5.5 will raise TypeError
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_fibonacci_string_raises_error(self):
        with pytest.raises(TypeError):
            fibonacci("5")

    def test_fibonacci_none_raises_error(self):
        with pytest.raises(TypeError):
            fibonacci(None)

    def test_fibonacci_list_raises_error(self):
        with pytest.raises(TypeError):
            fibonacci([5])


class TestIsPalindrome:
    """Tests for the is_palindrome function."""

    # Normal cases - palindromes
    def test_simple_palindrome(self):
        assert is_palindrome("racecar") is True

    def test_single_char(self):
        assert is_palindrome("a") is True

    def test_even_palindrome(self):
        assert is_palindrome("abba") is True

    def test_word_palindrome(self):
        assert is_palindrome("madam") is True

    def test_sentence_palindrome(self):
        # "nurses run" has an internal space, so stripped it's still "nurses run"
        # reversed: "nur sesrun" != "nurses run" -> not a palindrome
        assert is_palindrome("nurses run") is False

    def test_empty_string(self):
        assert is_palindrome("") is True

    # Normal cases - non-palindromes
    def test_non_palindrome(self):
        assert is_palindrome("hello") is False

    def test_two_different_chars(self):
        assert is_palindrome("ab") is False

    def test_non_palindrome_sentence(self):
        assert is_palindrome("hello world") is False

    # Case insensitive
    def test_uppercase_palindrome(self):
        assert is_palindrome("Racecar") is True

    def test_mixed_case_palindrome(self):
        assert is_palindrome("MaDaM") is True

    # Whitespace handling (strip is used)
    def test_leading_whitespace(self):
        assert is_palindrome("  racecar") is True

    def test_trailing_whitespace(self):
        assert is_palindrome("racecar  ") is True

    def test_both_whitespace(self):
        assert is_palindrome("  racecar  ") is True

    def test_spaces_in_middle(self):
        # "nurses run" has an internal space so is not a palindrome with this implementation
        assert is_palindrome("nurses run") is False

    # Edge cases
    def test_two_same_chars(self):
        assert is_palindrome("aa") is True

    def test_numbers_as_string(self):
        assert is_palindrome("121") is True

    def test_numbers_as_string_not_palindrome(self):
        assert is_palindrome("123") is False

    # Error cases
    def test_none_raises_error(self):
        with pytest.raises(AttributeError):
            is_palindrome(None)

    def test_int_raises_error(self):
        with pytest.raises(AttributeError):
            is_palindrome(121)

    def test_list_raises_error(self):
        with pytest.raises(AttributeError):
            is_palindrome(["a", "b", "a"])

    def test_bool_raises_error(self):
        with pytest.raises(AttributeError):
            is_palindrome(True)
