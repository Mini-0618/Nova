"""Tests for error handling in E35_errors.py."""
import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    """Test suite for BankAccount error handling."""

    def test_withdraw_success(self):
        """Test that a valid withdrawal reduces balance and returns it."""
        account = BankAccount(100)
        result = account.withdraw(30)
        assert result == 70
        assert account.balance == 70

    def test_withdraw_negative_amount_raises_value_error(self):
        """Test that withdrawing a negative amount raises ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(-10)
        assert str(exc_info.value) == 'Amount must be positive'

    def test_withdraw_zero_amount_raises_value_error(self):
        """Test that withdrawing zero raises ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(0)
        assert str(exc_info.value) == 'Amount must be positive'

    def test_withdraw_exceeding_balance_raises_insufficient_funds(self):
        """Test that over-withdrawal raises InsufficientFunds with correct message."""
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(100)
        assert str(exc_info.value) == 'Cannot withdraw 100, balance is 50'

    def test_insufficient_funds_is_exception_subclass(self):
        """Test that InsufficientFunds is a proper exception class."""
        assert issubclass(InsufficientFunds, Exception)

    def test_balance_unchanged_on_error(self):
        """Test that balance is not modified when an error is raised."""
        account = BankAccount(50)
        with pytest.raises((ValueError, InsufficientFunds)):
            account.withdraw(-5)
        assert account.balance == 50

        with pytest.raises((ValueError, InsufficientFunds)):
            account.withdraw(100)
        assert account.balance == 50
