import pytest
from E35_errors import BankAccount, InsufficientFunds

def test_withdraw_negative_amount():
    account = BankAccount(100)
    with pytest.raises(ValueError, match="Amount must be positive"):
        account.withdraw(-10)

def test_withdraw_zero_amount():
    account = BankAccount(100)
    with pytest.raises(ValueError, match="Amount must be positive"):
        account.withdraw(0)

def test_withdraw_insufficient_funds():
    account = BankAccount(50)
    with pytest.raises(InsufficientFunds, match="Cannot withdraw 100, balance is 50"):
        account.withdraw(100)

def test_withdraw_success():
    account = BankAccount(100)
    new_balance = account.withdraw(30)
    assert new_balance == 70
    assert account.balance == 70
