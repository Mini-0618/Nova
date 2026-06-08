"""Tests for error handling in E35_errors.py."""
import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    """Tests for BankAccount.withdraw error handling."""

    def test_withdraw_negative_amount_raises_valueerror(self):
        """Withdrawing a negative amount should raise ValueError."""
        account = BankAccount(balance=100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(-50)
        assert str(exc_info.value) == "Amount must be positive"

    def test_withdraw_zero_amount_raises_valueerror(self):
        """Withdrawing zero should raise ValueError."""
        account = BankAccount(balance=100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(0)
        assert str(exc_info.value) == "Amount must be positive"

    def test_withdraw_more_than_balance_raises_insufficientfunds(self):
        """Withdrawing more than the balance should raise InsufficientFunds."""
        account = BankAccount(balance=50)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(100)
        assert str(exc_info.value) == "Cannot withdraw 100, balance is 50"

    def test_withdraw_exact_balance_succeeds(self):
        """Withdrawing exactly the balance should succeed."""
        account = BankAccount(balance=100)
        result = account.withdraw(100)
        assert result == 0
        assert account.balance == 0

    def test_withdraw_less_than_balance_succeeds(self):
        """Withdrawing less than the balance should succeed."""
        account = BankAccount(balance=100)
        result = account.withdraw(30)
        assert result == 70
        assert account.balance == 70

    def test_insufficientfunds_is_exception(self):
        """InsufficientFunds should be a subclass of Exception."""
        assert issubclass(InsufficientFunds, Exception)

    def test_insufficientfunds_can_be_caught_as_exception(self):
        """InsufficientFunds should be catchable as a generic Exception."""
        account = BankAccount(balance=10)
        with pytest.raises(Exception) as exc_info:
            account.withdraw(20)
        assert isinstance(exc_info.value, InsufficientFunds)
