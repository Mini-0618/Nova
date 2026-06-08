"""Tests for E35_errors.py — verifying error handling."""

import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    """Test the BankAccount class error handling."""

    def test_withdraw_negative_amount_raises_value_error(self):
        """Withdrawing a negative amount should raise ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError, match="Amount must be positive"):
            account.withdraw(-10)

    def test_withdraw_zero_amount_raises_value_error(self):
        """Withdrawing zero should raise ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError, match="Amount must be positive"):
            account.withdraw(0)

    def test_withdraw_more_than_balance_raises_insufficient_funds(self):
        """Withdrawing more than the balance should raise InsufficientFunds."""
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds, match="Cannot withdraw 100, balance is 50"):
            account.withdraw(100)

    def test_withdraw_exact_balance_succeeds(self):
        """Withdrawing exactly the balance should succeed (no error)."""
        account = BankAccount(50)
        new_balance = account.withdraw(50)
        assert new_balance == 0
        assert account.balance == 0

    def test_withdraw_valid_amount_succeeds(self):
        """Withdrawing a valid amount should succeed."""
        account = BankAccount(100)
        new_balance = account.withdraw(30)
        assert new_balance == 70
        assert account.balance == 70

    def test_insufficient_funds_is_exception_subclass(self):
        """InsufficientFunds should be a subclass of Exception."""
        assert issubclass(InsufficientFunds, Exception)

    def test_insufficient_funds_can_be_caught_as_exception(self):
        """InsufficientFunds should be catchable as a generic Exception."""
        account = BankAccount(10)
        try:
            account.withdraw(20)
            pytest.fail("Expected InsufficientFunds exception")
        except Exception as e:
            assert isinstance(e, InsufficientFunds)
            assert str(e) == "Cannot withdraw 20, balance is 10"
