import pytest
from E35_errors import BankAccount, InsufficientFunds


# ---------------------------------------------------------------------------
# Tests for ValueError: non-positive amounts
# ---------------------------------------------------------------------------

class TestWithdrawNegativeAmount:
    """Verify ValueError is raised for negative amounts."""

    def test_raises_value_error(self):
        account = BankAccount(100)
        with pytest.raises(ValueError):
            account.withdraw(-10)

    def test_error_message(self):
        account = BankAccount(100)
        with pytest.raises(ValueError, match="Amount must be positive"):
            account.withdraw(-10)

    def test_different_negative_value(self):
        account = BankAccount(50)
        with pytest.raises(ValueError, match="Amount must be positive"):
            account.withdraw(-0.01)

    def test_large_negative_value(self):
        account = BankAccount(1000)
        with pytest.raises(ValueError, match="Amount must be positive"):
            account.withdraw(-999999)

    def test_balance_unchanged_after_error(self):
        account = BankAccount(100)
        with pytest.raises(ValueError):
            account.withdraw(-10)
        assert account.balance == 100


class TestWithdrawZeroAmount:
    """Verify ValueError is raised for zero amount."""

    def test_raises_value_error(self):
        account = BankAccount(100)
        with pytest.raises(ValueError):
            account.withdraw(0)

    def test_error_message(self):
        account = BankAccount(100)
        with pytest.raises(ValueError, match="Amount must be positive"):
            account.withdraw(0)

    def test_balance_unchanged_after_error(self):
        account = BankAccount(200)
        with pytest.raises(ValueError):
            account.withdraw(0)
        assert account.balance == 200


# ---------------------------------------------------------------------------
# Tests for InsufficientFunds: amount exceeds balance
# ---------------------------------------------------------------------------

class TestWithdrawInsufficientFunds:
    """Verify InsufficientFunds is raised when amount > balance."""

    def test_raises_insufficient_funds(self):
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds):
            account.withdraw(100)

    def test_error_message_contains_amount_and_balance(self):
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds, match="Cannot withdraw 100, balance is 50"):
            account.withdraw(100)

    def test_message_with_different_values(self):
        account = BankAccount(10)
        with pytest.raises(InsufficientFunds, match="Cannot withdraw 25, balance is 10"):
            account.withdraw(25)

    def test_message_with_zero_balance(self):
        account = BankAccount(0)
        with pytest.raises(InsufficientFunds, match="Cannot withdraw 1, balance is 0"):
            account.withdraw(1)

    def test_message_with_large_values(self):
        account = BankAccount(500)
        with pytest.raises(InsufficientFunds, match="Cannot withdraw 10000, balance is 500"):
            account.withdraw(10000)

    def test_balance_unchanged_after_error(self):
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds):
            account.withdraw(100)
        assert account.balance == 50

    def test_is_exception_subclass(self):
        """InsufficientFunds should be a subclass of Exception."""
        assert issubclass(InsufficientFunds, Exception)

    def test_is_not_value_error(self):
        """InsufficientFunds should NOT be a subclass of ValueError."""
        assert not issubclass(InsufficientFunds, ValueError)

    def test_exception_args_contain_message(self):
        """The exception's args should contain the formatted message."""
        account = BankAccount(30)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(80)
        assert exc_info.value.args[0] == "Cannot withdraw 80, balance is 30"


# ---------------------------------------------------------------------------
# Tests for successful withdrawals (boundary & normal cases)
# ---------------------------------------------------------------------------

class TestWithdrawSuccess:
    """Verify successful withdrawals work correctly."""

    def test_normal_withdrawal(self):
        account = BankAccount(100)
        new_balance = account.withdraw(30)
        assert new_balance == 70
        assert account.balance == 70

    def test_withdraw_entire_balance(self):
        """Withdrawing the exact balance should succeed (not raise InsufficientFunds)."""
        account = BankAccount(100)
        new_balance = account.withdraw(100)
        assert new_balance == 0
        assert account.balance == 0

    def test_withdraw_very_small_positive_amount(self):
        account = BankAccount(100)
        new_balance = account.withdraw(0.01)
        assert new_balance == pytest.approx(99.99)

    def test_default_balance_is_zero(self):
        account = BankAccount()
        assert account.balance == 0
        with pytest.raises(InsufficientFunds):
            account.withdraw(1)

    def test_multiple_withdrawals(self):
        account = BankAccount(200)
        account.withdraw(50)
        account.withdraw(30)
        account.withdraw(20)
        assert account.balance == 100

    def test_withdraw_after_insufficient_funds_does_not_corrupt_state(self):
        """Failed withdrawal should not affect balance for subsequent operations."""
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds):
            account.withdraw(200)
        # Balance should still be 50
        new_balance = account.withdraw(50)
        assert new_balance == 0
