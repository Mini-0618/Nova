import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    def test_withdraw_success(self):
        account = BankAccount(100)
        result = account.withdraw(50)
        assert result == 50
        assert account.balance == 50

    def test_withdraw_exact_balance(self):
        account = BankAccount(100)
        result = account.withdraw(100)
        assert result == 0
        assert account.balance == 0

    def test_withdraw_negative_amount_raises_valueerror(self):
        account = BankAccount(100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(-10)
        assert str(exc_info.value) == 'Amount must be positive'

    def test_withdraw_zero_amount_raises_valueerror(self):
        account = BankAccount(100)
        with pytest.raises(ValueError) as exc_info:
            account.withdraw(0)
        assert str(exc_info.value) == 'Amount must be positive'

    def test_withdraw_insufficient_funds_raises_exception(self):
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(100)
        assert str(exc_info.value) == 'Cannot withdraw 100, balance is 50'

    def test_insufficient_funds_is_exception_subclass(self):
        assert issubclass(InsufficientFunds, Exception)

    def test_withdraw_zero_balance_raises_insufficient_funds(self):
        account = BankAccount(0)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(1)
        assert str(exc_info.value) == 'Cannot withdraw 1, balance is 0'

    def test_balance_unchanged_on_error(self):
        account = BankAccount(50)
        with pytest.raises((ValueError, InsufficientFunds)):
            account.withdraw(100)
        assert account.balance == 50
