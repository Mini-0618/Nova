#!/usr/bin/env python3
"""E35: Tests for error handling in E35_errors.py."""
import sys
sys.path.insert(0, '.')

from E35_errors import BankAccount, InsufficientFunds
import traceback

def test_withdraw_positive():
    """Test that withdrawing a positive amount works."""
    account = BankAccount(100)
    assert account.withdraw(50) == 50

def test_withdraw_negative():
    """Test that withdrawing negative amount raises ValueError."""
    account = BankAccount(100)
    try:
        account.withdraw(-10)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "positive" in str(e).lower()

def test_withdraw_insufficient():
    """Test that withdrawing more than balance raises InsufficientFunds."""
    account = BankAccount(50)
    try:
        account.withdraw(100)
        assert False, "Should have raised InsufficientFunds"
    except InsufficientFunds as e:
        assert "100" in str(e)
        assert "50" in str(e)

def test_withdraw_exact_balance():
    """Test that withdrawing exact balance works."""
    account = BankAccount(100)
    assert account.withdraw(100) == 0

if __name__ == '__main__':
    test_withdraw_positive()
    test_withdraw_negative()
    test_withdraw_insufficient()
    test_withdraw_exact_balance()
    print('ALL TESTS PASSED')
