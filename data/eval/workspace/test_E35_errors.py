"""Tests for error handling in E35_errors.py.

Tests that:
1. InsufficientFunds exception is raised with the right message
2. ValueError is raised for non-positive amounts
3. Successful withdrawals work correctly
"""
import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    """Test suite for BankAccount error handling."""

    def test_insufficient_funds_exception_message(self):
        """Verify InsufficientFunds is raised with the correct message."""
        account = BankAccount(balance=50)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(100)
        expected = "Cannot withdraw 100, balance is 50"
        assert str(exc_info.value) == expected, (
            f"Expected '{expected}', got '{str(exc_info.value)}'"
        )

    def test_insufficient_funds_exception_type(self):
        """Verify InsufficientFunds is a proper Exception subclass."""
        assert issubclass(InsufficientFunds, Exception), (
            "InsufficientFunds must inherit from Exception"
        )

    def test_zero_amount_raises_value_error(self):
        """Verify withdrawing 0 raises ValueError."""
        account = BankAccount(balance=100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(0)
        assert str(exc_info.value) == "Amount must be positive"

    def test_negative_amount_raises_value_error(self):
        """Verify withdrawing a negative amount raises ValueError."""
        account = BankAccount(balance=100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(-10)
        assert str(exc_info.value) == "Amount must be positive"

    def test_value_error_on_empty_account(self):
        """Verify ValueError is still raised even on empty account."""
        account = BankAccount(balance=0)
        with pytest.raises(ValueError):
            account.withdraw(0)

    def test_successful_withdrawal_returns_balance(self):
        """Verify a valid withdrawal returns the new balance."""
        account = BankAccount(balance=100)
        new_balance = account.withdraw(30)
        assert new_balance == 70, f"Expected 70, got {new_balance}"
        assert account.balance == 70, f"Expected balance 70, got {account.balance}"

    def test_exact_balance_withdrawal(self):
        """Verify withdrawing the exact balance is allowed."""
        account = BankAccount(balance=50)
        new_balance = account.withdraw(50)
        assert new_balance == 0
        assert account.balance == 0

    def test_insufficient_funds_with_zero_balance(self):
        """Verify InsufficientFunds when balance is 0 and amount > 0."""
        account = BankAccount(balance=0)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(1)
        expected = "Cannot withdraw 1, balance is 0"
        assert str(exc_info.value) == expected

    def test_insufficient_funds_with_different_amounts(self):
        """Verify the exception message correctly formats different amounts."""
        account = BankAccount(balance=10)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(20)
        assert "20" in str(exc_info.value)
        assert "10" in str(exc_info.value)

    def test_default_balance_is_zero(self):
        """Verify a new account defaults to balance 0."""
        account = BankAccount()
        assert account.balance == 0
