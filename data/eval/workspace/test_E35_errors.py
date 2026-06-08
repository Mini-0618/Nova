"""Tests for E35_errors.py — verifying error handling."""
import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    """Test the BankAccount class's error handling."""

    def test_withdraw_negative_amount(self):
        """Withdrawing a negative amount should raise ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError) as excinfo:
            account.withdraw(-50)
        assert str(excinfo.value) == 'Amount must be positive'

    def test_withdraw_zero_amount(self):
        """Withdrawing zero should raise ValueError."""
        account = BankAccount(100)
        with pytest.raises(ValueError) as excinfo:
            account.withdraw(0)
        assert str(excinfo.value) == 'Amount must be positive'

    def test_withdraw_insufficient_funds(self):
        """Withdrawing more than the balance should raise InsufficientFunds."""
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds) as excinfo:
            account.withdraw(100)
        expected_msg = 'Cannot withdraw 100, balance is 50'
        assert str(excinfo.value) == expected_msg

    def test_withdraw_exact_balance(self):
        """Withdrawing exactly the balance should succeed (no error)."""
        account = BankAccount(100)
        result = account.withdraw(100)
        assert result == 0
        assert account.balance == 0

    def test_withdraw_success(self):
        """Withdrawing a valid amount should deduct and return new balance."""
        account = BankAccount(200)
        result = account.withdraw(50)
        assert result == 150
        assert account.balance == 150

    def test_insufficient_funds_exception_type(self):
        """InsufficientFunds should be a subclass of Exception."""
        assert issubclass(InsufficientFunds, Exception)

    def test_insufficient_funds_can_be_caught_as_exception(self):
        """InsufficientFunds should be catchable as a generic Exception."""
        account = BankAccount(10)
        try:
            account.withdraw(100)
        except Exception as e:
            assert isinstance(e, InsufficientFunds)
            assert str(e) == 'Cannot withdraw 100, balance is 10'
        else:
            pytest.fail("Expected InsufficientFunds exception")
