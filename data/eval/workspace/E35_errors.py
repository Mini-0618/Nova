class InsufficientFunds(Exception): pass

class BankAccount:
    def __init__(self, balance=0):
        self.balance = balance
    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError('Amount must be positive')
        if amount > self.balance:
            raise InsufficientFunds(f'Cannot withdraw {amount}, balance is {self.balance}')
        self.balance -= amount
        return self.balance