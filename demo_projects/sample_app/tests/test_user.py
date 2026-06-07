"""Test user model"""
import pytest
from models.user import User, create_user

def test_create_user():
    user = create_user("Alice", "alice@example.com")
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.id == 1

def test_greet():
    user = User(id=1, name="Bob", email="bob@example.com")
    assert user.greet() == "Hello, Bob!"