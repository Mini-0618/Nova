"""Tests for E31_target.py — fibonacci and is_palindrome functions."""

import pytest
from E31_target import fibonacci, is_palindrome


# ============================================================
# Tests for fibonacci(n)
# ============================================================

class TestFibonacci:
    """Normal cases — typical inputs."""

    @pytest.mark.parametrize("n, expected", [
        (0, 0),
        (1, 1),
        (2, 1),
        (3, 2),
        (4, 3),
        (5, 5),
        (6, 8),
        (7, 13),
        (10, 55),
        (20, 6765),
        (30, 832040),
    ])
    def test_normal_cases(self, n, expected):
        assert fibonacci(n) == expected

    """Edge cases."""

    def test_large_input(self):
        # fibonacci(100) = 354224848179261915075
        assert fibonacci(100) == 354224848179261915075

    def test_consecutive_values(self):
        for i in range(2, 20):
            assert fibonacci(i) == fibonacci(i - 1) + fibonacci(i - 2)

    """Error cases."""

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-1)

    def test_negative_large_raises(self):
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(-100)

    @pytest.mark.parametrize("bad_input", [-1, -5, -1000])
    def test_multiple_negative_inputs(self, bad_input):
        with pytest.raises(ValueError, match="n must be non-negative"):
            fibonacci(bad_input)

    def test_non_integer_input(self):
        with pytest.raises(TypeError):
            fibonacci("10")

    def test_float_input(self):
        with pytest.raises(TypeError):
            fibonacci(5.5)

    def test_none_input(self):
        with pytest.raises(TypeError):
            fibonacci(None)


# ============================================================
# Tests for is_palindrome(s)
# ============================================================

class TestIsPalindrome:
    """Normal cases — typical inputs."""

    @pytest.mark.parametrize("s, expected", [
        ("racecar", True),
        ("hello", False),
        ("a", True),
        ("", True),
        ("madam", True),
        ("noon", True),
        ("python", False),
    ])
    def test_normal_cases(self, s, expected):
        assert is_palindrome(s) == expected

    """Edge cases — case insensitivity and whitespace."""

    @pytest.mark.parametrize("s", [
        "Racecar",
        "RACECAR",
        "racecaR",
        "Madam",
        "Noon",
    ])
    def test_case_insensitivity(self, s):
        assert is_palindrome(s) is True

    @pytest.mark.parametrize("s, expected", [
        ("  racecar  ", True),
        ("  hello  ", False),
        ("\tnoon\n", True),
        ("  a  ", True),
    ])
    def test_whitespace_handling(self, s, expected):
        assert is_palindrome(s) == expected

    def test_mixed_case_with_spaces(self):
        assert is_palindrome("  Racecar  ") is True

    def test_single_character(self):
        assert is_palindrome("z") is True

    def test_empty_string(self):
        assert is_palindrome("") is True

    def test_string_with_only_spaces(self):
        assert is_palindrome("   ") is True

    """Error cases."""

    def test_non_string_input(self):
        with pytest.raises(AttributeError):
            is_palindrome(12345)

    def test_none_input(self):
        with pytest.raises(AttributeError):
            is_palindrome(None)

    def test_list_input(self):
        with pytest.raises(AttributeError):
            is_palindrome(["racecar"])

    @pytest.mark.parametrize("bad_input", [123, 45.6, True, ["a"], {"key": "val"}])
    def test_various_non_string_inputs(self, bad_input):
        with pytest.raises((AttributeError, TypeError)):
            is_palindrome(bad_input)
