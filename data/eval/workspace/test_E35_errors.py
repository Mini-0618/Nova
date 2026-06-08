import pytest
from E35_errors import BankAccount, InsufficientFunds


class TestBankAccount:
    def test_initial_balance(self):
        """Test default and custom initial balance."""
        account = BankAccount()
        assert account.balance == 0

        account = BankAccount(100)
        assert account.balance == 100

    def test_withdraw_success(self):
        """Test successful withdrawal reduces balance."""
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

    def test_withdraw_exceeds_balance_raises_insufficient_funds(self):
        """Test that withdrawing more than balance raises InsufficientFunds."""
        account = BankAccount(50)
        with pytest.raises(InsufficientFunds) as exc_info:
            account.withdraw(100)
        assert str(exc_info.value) == 'Cannot withdraw 100, balance is 50'

    def test_insufficient_funds_is_exception(self):
        """Test that InsufficientFunds is a subclass of Exception."""
        assert issubclass(InsufficientFunds, Exception)

    def test_balance_unchanged_on_error(self):
        """Test that balance is not modified when an error is raised."""
        account = BankAccount(50)
        with pytest.raises(ValueError):
            account.withdraw(-5)
        assert account.balance == 50

        with pytest.raises(InsufficientFunds):
            account.withdraw(100)
        assert account.balance == 50
