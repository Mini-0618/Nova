"""Tests for error handling in E35_errors.py"""
import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccountErrors:
    """Test that the right exceptions are raised with the right messages."""

    def test_withdraw_negative_amount_raises_value_error(self):
        """Withdrawing a negative amount should raise ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(-50)
        assert str(exc_info.value) == 'Amount must be positive'

    def test_withdraw_zero_amount_raises_value_error(self):
        """Withdrawing zero should raise ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(0)
        assert str(exc_info.value) == 'Amount must be positive'

    def test_withdraw_more_than_balance_raises_insufficient_funds(self):
        """Withdrawing more than balance should raise InsufficientFunds."""
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(100)
        assert str(exc_info.value) == 'Cannot withdraw 100, balance is 50'

    def test_withdraw_exact_balance_succeeds(self):
        """Withdrawing exactly the balance should succeed."""
        account = BankAccount(100)
        result = account.withdraw(100)
        assert result == 0
        assert account.balance == 0

    def test_withdraw_less_than_balance_succeeds(self):
        """Withdrawing less than balance should succeed."""
        account = BankAccount(100)
        result = account.withdraw(30)
        assert result == 70
        assert account.balance == 70

    def test_insufficient_funds_is_exception_subclass(self):
        """InsufficientFunds should be a proper Exception subclass."""
        assert issubclass(InsufficientFunds, Exception)

    def test_multiple_withdrawals_until_empty(self):
        """Multiple withdrawals should work correctly, and overdrawing at the end should fail."""
        account = BankAccount(100)
        account.withdraw(40)
        assert account.balance == 60
        account.withdraw(60)
        assert account.balance == 0
        with pytest.raises(InsufficientFunds):
            account.withdraw(1)
